#!/usr/bin/env python3
"""Tests for doctor_probes: the feedback capability probe, the feedback
directory check, the capture self-containment scan and the bookkeeping index
read-gate scan.

This module opts out of the autouse `gh` stub in conftest (the stub is skipped
for `test_doctor_probes`), so a test that reaches the real `_gh_environment`
mocks `shutil.which`, `_known_gh_locations` and `subprocess.run` itself. The
`subprocess.run` wrapper from conftest stays active, so a stray `gh` spawn
still fails the test at teardown.

Run with:  python -m pytest tests/test_doctor_probes.py -q
"""

import contextlib
import io
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

# Allow imports whether pytest is launched from the repo root or scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import config_loader
import doctor_probes as dp
import init_project as ip

WARN_BYTES = 60_000  # past the 22,000-token warn line, under the 25,000-token page cap


def _project(tmp_path, *, lessons=True, feedback=None, index_files=None):
    """Write a minimal project and return its parsed config dict."""
    planwise = tmp_path / "project" / "planwise"
    planwise.mkdir(parents=True)
    lines = ['plugin_version: "1.0.4"', "project:", "  name: Fixture", "  backlog_dir: Backlog", "  plans_dir: Plans"]
    if lessons:
        lines.append("  lessons_dir: LessonsLearned")
    if index_files:
        lines.append("  index_files:")
        lines += [f"    {family}: {name}" for family, name in index_files.items()]
    if feedback is not None:
        lines += ["feedback:", f"  enabled: {'true' if feedback else 'false'}"]
    (planwise / "config.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    for name in ("Backlog", "Plans") + (("LessonsLearned",) if lessons else ()):
        (planwise / name).mkdir()
    return config_loader.load_config(config_path=planwise / "config.yaml")


def _run(func, config):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        func(config)
    return buf.getvalue()


def _gh_calls(auth_rc=0):
    """A `subprocess.run` stand-in: `gh --version` succeeds, `gh auth status` exits auth_rc."""
    def fake(args, **_kwargs):
        if "--version" in args:
            return subprocess.CompletedProcess(args, 0, "gh version 2.40.0 (2024-01-01)\n", "")
        return subprocess.CompletedProcess(args, auth_rc, "", "")
    return fake


def _probe_stage_16(config, *, on_path, locations=(), auth_rc=0):
    which = "/fake/bin/gh" if on_path else None
    with (
        mock.patch("doctor_probes.shutil.which", return_value=which),
        mock.patch.object(dp, "_known_gh_locations", return_value=list(locations)),
        mock.patch("doctor_probes.subprocess.run", side_effect=_gh_calls(auth_rc)),
    ):
        return _run(dp._stage_16, config)


# --- Stage 16 ---------------------------------------------------------------

def test_stage_16_gh_on_path_and_authenticated(tmp_path):
    out = _probe_stage_16(_project(tmp_path, feedback=True), on_path=True)
    assert "gh resolvable:     yes — on PATH  gh version 2.40.0" in out
    assert "gh authenticated:  yes" in out
    assert "Upstream posting: ENABLED — reports post directly" in out


def test_stage_16_known_location_prints_the_note(tmp_path):
    fake_gh = tmp_path / "gh.exe"
    fake_gh.write_text("", encoding="utf-8")
    out = _probe_stage_16(_project(tmp_path, feedback=True), on_path=False, locations=[fake_gh])
    assert f"yes — at {fake_gh}" in out
    assert f"gh found at {fake_gh}, not on this session's PATH — a new terminal will resolve it" in out
    assert "ENABLED" in out


def test_stage_16_gh_absent(tmp_path):
    out = _probe_stage_16(_project(tmp_path, feedback=True), on_path=False)
    assert "gh resolvable:     no" in out
    assert "gh authenticated:  n/a — gh absent" in out
    assert "gh not found on PATH or at a known install location" in out
    assert "Upstream posting: DRAFT-ONLY" in out


def test_stage_16_gh_unauthenticated(tmp_path):
    out = _probe_stage_16(_project(tmp_path, feedback=True), on_path=True, auth_rc=1)
    assert "gh authenticated:  no" in out
    assert "gh is installed but not authenticated — run: gh auth login" in out
    assert "Upstream posting: DRAFT-ONLY" in out


def test_stage_16_feedback_disabled_prints_the_remedy(tmp_path):
    out = _probe_stage_16(_project(tmp_path, feedback=False), on_path=True)
    assert "feedback.enabled:  false" in out
    assert "feedback.enabled is false — /planwise feedback drafts locally and posts nothing" in out
    assert "Upstream posting: DRAFT-ONLY" in out


def _gh_fake(broken=(), hang=()):
    """A `subprocess.run` stand-in keyed on the executable. `broken` executables
    exit 1 on every call, `hang` ones raise a timeout, the rest behave as a healthy gh."""
    def fake(args, **_kwargs):
        exe = str(args[0])
        if exe in hang:
            raise subprocess.TimeoutExpired(args, 5)
        if exe in broken:
            return subprocess.CompletedProcess(args, 1, "", "broken shim")
        return _gh_calls()(args)
    return fake


def _probe_with(config, fake, *, which=None, locations=()):
    with (
        mock.patch("doctor_probes.shutil.which", return_value=which),
        mock.patch.object(dp, "_known_gh_locations", return_value=list(locations)),
        mock.patch("doctor_probes.subprocess.run", side_effect=fake),
    ):
        return _run(dp._stage_16, config)


def test_stage_16_broken_path_shim_falls_through_to_a_known_location(tmp_path):
    shim = str(Path("/fake/bin/gh"))
    good = tmp_path / "gh.exe"
    good.write_text("", encoding="utf-8")
    out = _probe_with(_project(tmp_path, feedback=True), _gh_fake(broken=(shim,)), which=shim, locations=[good])
    assert f"yes — at {good}" in out
    assert "not on this session's PATH" in out
    assert "ENABLED" in out


def test_stage_16_broken_first_candidate_falls_through_to_the_next(tmp_path):
    first, second = tmp_path / "first" / "gh.exe", tmp_path / "second" / "gh.exe"
    for candidate in (first, second):
        candidate.parent.mkdir()
        candidate.write_text("", encoding="utf-8")
    out = _probe_with(_project(tmp_path, feedback=True), _gh_fake(broken=(str(first),)), locations=[first, second])
    assert f"yes — at {second}" in out
    assert str(first) not in out
    assert "ENABLED" in out


def test_stage_16_every_candidate_broken_reports_gh_not_found(tmp_path):
    shim = str(Path("/fake/bin/gh"))
    out = _probe_with(_project(tmp_path, feedback=True), _gh_fake(broken=(shim,)), which=shim)
    assert "gh resolvable:     no" in out
    assert "gh not found on PATH or at a known install location" in out
    assert "did not answer" not in out


def test_stage_16_timeout_on_version_is_not_reported_as_gh_not_found(tmp_path):
    shim = str(Path("/fake/bin/gh"))
    out = _probe_with(_project(tmp_path, feedback=True), _gh_fake(hang=(shim,)), which=shim)
    assert "gh did not answer within 5 s" in out
    assert "re-run /planwise doctor" in out
    assert "gh not found" not in out
    assert "not authenticated" not in out
    assert "Upstream posting: DRAFT-ONLY" in out


def test_stage_16_timeout_on_auth_is_not_reported_as_not_authenticated(tmp_path):
    def fake(args, **_kwargs):
        if "auth" in args:
            raise subprocess.TimeoutExpired(args, 5)
        return _gh_calls()(args)

    out = _probe_with(_project(tmp_path, feedback=True), fake, which="/fake/bin/gh")
    assert "gh did not answer within 5 s" in out
    assert "not authenticated" not in out
    assert "gh auth login" not in out
    assert "Upstream posting: DRAFT-ONLY" in out


# --- Stage 17 ---------------------------------------------------------------

def test_stage_17_directory_present(tmp_path):
    config = _project(tmp_path)
    Path(config["_feedback_dir"]).mkdir()
    out = _run(dp._stage_17, config)
    assert "exists:               yes" in out
    assert "— present." in out
    assert "is absent" not in out


def test_stage_17_directory_absent(tmp_path):
    out = _run(dp._stage_17, _project(tmp_path))
    assert "exists:               no" in out
    assert "! feedback directory is absent" in out
    assert "/planwise doctor --create-feedback-dir" in out


# --- Step 7 -----------------------------------------------------------------

def test_step_7_pointer_without_a_fence_is_flagged(tmp_path):
    config = _project(tmp_path)
    (Path(config["_backlog_dir"]) / "BB-001-Pointer.md").write_text(
        "---\nid: 1\n---\nSee the diff in session notes at /Users/someone/notes.txt\n", encoding="utf-8")
    out = _run(dp._step_7, config)
    assert "Capture self-containment (advisory):" in out
    assert "~ Backlog/BB-001-Pointer.md" in out
    assert "/Users/someone/notes.txt" in out


def test_step_7_pointer_with_a_fence_is_clean(tmp_path):
    config = _project(tmp_path)
    (Path(config["_backlog_dir"]) / "BB-001-Fenced.md").write_text(
        "Notes live at /Users/someone/notes.txt\n\n```\nthe inlined spec\n```\n", encoding="utf-8")
    out = _run(dp._step_7, config)
    assert "all scanned captures inline their substance" in out


def test_step_7_in_project_absolute_path_is_not_flagged(tmp_path):
    config = _project(tmp_path)
    backlog = Path(config["_backlog_dir"])
    inside = Path(config["_project_root"]) / "src" / "module.py"
    outside = tmp_path / "elsewhere" / "module.py"
    (backlog / "BB-001-Inside.md").write_text(f"The change lives in {inside} today.\n", encoding="utf-8")
    (backlog / "BB-002-Outside.md").write_text(f"The change lives in {outside} today.\n", encoding="utf-8")
    out = _run(dp._step_7, config)
    assert "BB-002-Outside.md" in out
    assert "BB-001-Inside.md" not in out


def test_step_7_archive_directory_is_excluded(tmp_path):
    config = _project(tmp_path)
    archive = Path(config["_backlog_dir"]) / "Archive"
    archive.mkdir()
    (archive / "BB-003-Closed.md").write_text("See the diff in session X at /home/someone/x\n", encoding="utf-8")
    out = _run(dp._step_7, config)
    assert "BB-003-Closed.md" not in out
    assert "all scanned captures inline their substance" in out


def test_step_7_capture_outside_the_planwise_root_prints_without_raising(tmp_path):
    config = dict(_project(tmp_path))
    elsewhere = tmp_path / "elsewhere" / "Backlog"
    elsewhere.mkdir(parents=True)
    config["_backlog_dir"] = elsewhere
    (elsewhere / "BB-009-Away.md").write_text("See the diff in session notes at /Users/x/n.txt\n", encoding="utf-8")
    out = _run(dp._step_7, config)
    assert f"~ {(elsewhere / 'BB-009-Away.md').as_posix()}" in out


def test_path_token_pattern_is_case_insensitive_and_matches_the_git_bash_drive_form():
    text = "a /c/Users/someone/n.txt b /D/Work/y c C:\\USERS\\z d /USERS/a/b e /home/q"
    tokens = [m.group(0) for m in dp._PATH_TOKEN_RE.finditer(text)]
    assert tokens == ["/c/Users/someone/n.txt", "/D/Work/y", "C:\\USERS\\z", "/USERS/a/b", "/home/q"]


def test_step_7_git_bash_drive_path_outside_the_project_is_flagged(tmp_path):
    config = _project(tmp_path)
    (Path(config["_backlog_dir"]) / "BB-004-GitBash.md").write_text(
        "The notes live at /c/Users/someone/notes.txt today.\n", encoding="utf-8")
    out = _run(dp._step_7, config)
    assert "BB-004-GitBash.md" in out
    assert "pointer:  /c/Users/someone/notes.txt" in out


@pytest.mark.skipif(sys.platform != "win32", reason="a Git-Bash drive path only names a project on Windows")
def test_step_7_git_bash_drive_path_inside_the_project_is_not_flagged(tmp_path):
    config = _project(tmp_path)
    posix = Path(config["_project_root"]).as_posix()
    git_bash = f"/{posix[0].lower()}{posix[2:]}/src/module.py"
    (Path(config["_backlog_dir"]) / "BB-005-Inside.md").write_text(f"It lives in {git_bash} today.\n", encoding="utf-8")
    out = _run(dp._step_7, config)
    assert "BB-005-Inside.md" not in out
    assert "all scanned captures inline their substance" in out


@pytest.mark.skipif(sys.platform != "win32", reason="a Git-Bash drive path only names a project on Windows")
def test_inside_normalises_a_git_bash_drive_path_before_comparing_to_the_root():
    assert dp._inside("/c/Users/x/proj/src/a.py", "C:\\Users\\x\\proj")
    assert dp._inside("/C/Users/x/proj", "c:/users/x/proj")
    assert not dp._inside("/c/Users/x/other/a.py", "C:\\Users\\x\\proj")


# --- Step 8 -----------------------------------------------------------------

def test_step_8_index_naming_receives_a_path(tmp_path):
    config = _project(tmp_path)
    with mock.patch.object(dp, "_index_naming", wraps=dp._index_naming) as naming:
        out = _run(dp._step_8, config)
    assert "Bookkeeping indexes:" in out
    assert naming.call_count >= 2  # the backlog hub and the lessons hub
    assert all(isinstance(call.args[0], Path) for call in naming.call_args_list)


def test_step_8_custom_backlog_hub_is_recognised(tmp_path):
    config = _project(tmp_path, index_files={"backlog": "Backlog-Index.md"})
    backlog = Path(config["_backlog_dir"])
    (backlog / "Backlog-Index.md").write_text("hub\n", encoding="utf-8")
    (backlog / "Backlog-Index-001-050.md").write_bytes(b"x" * (WARN_BYTES - 1) + b"\n")
    out = _run(dp._step_8, config)
    assert "backlog:  2 file(s) scanned" in out
    assert "[Warn / reason=read] Backlog/Backlog-Index-001-050.md" in out


def test_step_8_over_warn_file_reports_level_and_reason(tmp_path):
    config = _project(tmp_path)
    plans = Path(config["_plans_index"])
    plans.write_bytes((b"x" * 59 + b"\n") * (WARN_BYTES // 60))
    out = _run(dp._step_8, config)
    assert "[Warn / reason=read] Plans/00-Index-Plans.md" in out
    assert "size: 60000 B" in out
    assert "No known-condition note recorded" in out
    assert "all Green" not in out


def test_step_8_prints_the_known_condition_line(tmp_path):
    config = _project(tmp_path)
    plans = Path(config["_plans_index"])
    plans.write_bytes(b"<!-- known-condition: the index split is tracked -->\n" + (b"x" * 59 + b"\n") * (WARN_BYTES // 60))
    out = _run(dp._step_8, config)
    assert "Known condition: the index split is tracked" in out
    assert "No known-condition note recorded" not in out


def test_step_8_resolves_the_lessons_changelog_and_promotion_log_families(tmp_path):
    config = _project(tmp_path)
    lessons = Path(config["_lessons_dir"])
    (lessons / "Archive").mkdir()
    members = [
        "00-Index-LessonsLearned.md",
        "00-Changelog-LessonsLearned.md",
        "00-Changelog-LessonsLearned-Part-02.md",
        "00-Changelog-LessonsLearned-Archive-2026.md",
        "00-Changelog-LessonsLearned-Archive-2026-Part-02.md",
        "00-PromotionLog-LessonsLearned.md",
        "Archive/PromotionLog-LessonsLearned-001-050.md",
    ]
    for name in members:
        (lessons / name).write_text("x\n", encoding="utf-8")
    # Not family members: a stray archive suffix and a lesson file.
    (lessons / "00-Changelog-LessonsLearned-Archive-2026_bak.md").write_text("x\n", encoding="utf-8")
    (lessons / "LL-001-Lesson.md").write_text("x\n", encoding="utf-8")
    out = _run(dp._step_8, config)
    assert f"lessons:  {len(members)} file(s) scanned" in out


def test_step_8_a_missing_middle_part_does_not_hide_the_later_parts(tmp_path):
    config = _project(tmp_path)
    lessons = Path(config["_lessons_dir"])
    members = [
        "00-Index-LessonsLearned.md",
        "00-Changelog-LessonsLearned.md",
        "00-Changelog-LessonsLearned-Part-03.md",
        "00-Changelog-LessonsLearned-Archive-2026.md",
        "00-Changelog-LessonsLearned-Archive-2026-Part-04.md",
    ]
    for name in members:
        (lessons / name).write_text("x\n", encoding="utf-8")
    out = _run(dp._step_8, config)
    assert f"lessons:  {len(members)} file(s) scanned" in out


def test_step_8_none_lessons_dir_skips_the_lessons_rows(tmp_path):
    config = _project(tmp_path, lessons=False)
    out = _run(dp._step_8, config)
    assert "lessons:  skipped — project.lessons_dir is absent" in out
    assert "companion:" not in out


# --- The call site ----------------------------------------------------------

def test_run_doctor_prints_the_probe_banners_without_spawning_gh(tmp_path):
    config = _project(tmp_path, feedback=True)
    plugin_root = tmp_path / "plugin"
    plugin_root.mkdir()
    cfg = ip.InitConfig(project_name="Fixture", project_root=Path(config["_project_root"]), plugin_root=plugin_root)
    cfg.plugin_version = "1.0.4"
    gh_spawns = []

    def fake_run(args, **_kwargs):
        if Path(str(args[0])).stem.lower() == "gh":
            gh_spawns.append(args)
        return subprocess.CompletedProcess(args, 1, "", "")

    buf = io.StringIO()
    with (
        mock.patch("doctor_probes.shutil.which", return_value=None),
        mock.patch.object(dp, "_known_gh_locations", return_value=[]),
        mock.patch("doctor_probes.subprocess.run", side_effect=fake_run),
        contextlib.redirect_stdout(buf),
    ):
        exit_code = ip._run_doctor(cfg)
    out = buf.getvalue()
    assert exit_code == 0
    assert gh_spawns == []
    for banner in (
        "planwise doctor — feedback capability probe",
        "planwise doctor — feedback directory presence check",
        "planwise doctor — bookkeeping index read-gate scan",
    ):
        assert banner in out
    assert "Capture self-containment" in out


# --- The gh seam ------------------------------------------------------------

def test_stage_16_reads_gh_only_through_the_seam(tmp_path):
    config = _project(tmp_path, feedback=True)
    env = {"path": Path("/fake/bin/gh"), "note": "", "version": "gh version 9.9.9", "authenticated": True}
    with (
        mock.patch.object(dp, "_gh_environment", return_value=env) as seam,
        mock.patch("doctor_probes.shutil.which") as which,
        mock.patch("doctor_probes.subprocess.run") as run,
    ):
        out = _run(dp._stage_16, config)
    seam.assert_called_once_with()
    which.assert_not_called()
    run.assert_not_called()
    assert "gh version 9.9.9" in out
    assert "ENABLED" in out


@pytest.mark.parametrize("command", ["gh --version", '"/opt/Git Hub/gh" auth status'])
def test_the_gh_tripwire_fires_on_a_string_command(_no_real_gh, command):
    # A string command (shell=True) names its executable in the first token.
    with pytest.raises(RuntimeError, match="gh"):
        subprocess.run(command, shell=True, check=False)
    assert _no_real_gh == [[command]]
    _no_real_gh.clear()  # teardown asserts the list is empty


def test_the_gh_tripwire_fires_on_a_spawn(_no_real_gh):
    # The control: the autouse wrapper must refuse a gh spawn and record it.
    try:
        subprocess.run(["gh", "--version"], check=False)
    except RuntimeError as exc:
        assert "gh" in str(exc)
    else:
        raise AssertionError("the wrapper let a gh spawn through")
    assert len(_no_real_gh) == 1
    _no_real_gh.clear()  # teardown asserts the list is empty
