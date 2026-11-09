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
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import pytest

# Allow imports whether pytest is launched from the repo root or scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import config_loader
import doctor_probes as dp
import feedback_drafts as fd
import gitignore_entry as ge
import init_project as ip

WARN_BYTES = 60_000  # past the 22,000-token warn line, under the 25,000-token page cap


def _project(tmp_path, *, lessons=True, feedback=None, index_files=None, drafts=None):
    """Write a minimal project and return its parsed config dict. `drafts` is
    written verbatim, so a bare `off` reaches PyYAML as a boolean."""
    planwise = tmp_path / "project" / "planwise"
    planwise.mkdir(parents=True)
    lines = ['plugin_version: "1.0.4"', "project:", "  name: Fixture", "  backlog_dir: Backlog", "  plans_dir: Plans"]
    if lessons:
        lines.append("  lessons_dir: LessonsLearned")
    if index_files:
        lines.append("  index_files:")
        lines += [f"    {family}: {name}" for family, name in index_files.items()]
    if feedback is not None or drafts is not None:
        lines.append("feedback:")
    if feedback is not None:
        lines.append(f"  enabled: {'true' if feedback else 'false'}")
    if drafts is not None:
        lines.append(f"  drafts: {drafts}")
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


@pytest.mark.parametrize(
    ("drafts", "expected"),
    [(None, "notify"), ("quiet", "quiet"), ("off", "off")],
)
def test_stage_16_prints_the_feedback_drafts_value(tmp_path, drafts, expected):
    # A bare `off` is a YAML boolean; the line must read it through the loader.
    out = _probe_stage_16(_project(tmp_path, feedback=True, drafts=drafts), on_path=True)
    assert f"feedback.drafts:   {expected}" in out


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
    assert "absent" not in out
    assert "is not set" not in out


_ABSENT_LINE = "feedback.enabled:  absent (not set, read as false)"
_ABSENT_REMEDY = "feedback.enabled is not set — an interactive /planwise feedback run offers to enable posting"
_DISABLED_REMEDY = "feedback.enabled is false — /planwise feedback drafts locally and posts nothing"


def test_stage_16_absent_key_without_a_feedback_block_prints_its_own_line_and_remedy(tmp_path):
    out = _probe_stage_16(_project(tmp_path), on_path=True)
    assert _ABSENT_LINE in out
    assert f"{_ABSENT_REMEDY}, or set feedback.enabled: true in config.yaml" in out
    assert _DISABLED_REMEDY not in out
    assert "feedback.enabled:  false" not in out
    assert "Upstream posting: DRAFT-ONLY" in out


def test_stage_16_absent_key_inside_a_feedback_block_prints_its_own_line_and_remedy(tmp_path):
    out = _probe_stage_16(_project(tmp_path, drafts="quiet"), on_path=True)
    assert _ABSENT_LINE in out
    assert _ABSENT_REMEDY in out
    assert _DISABLED_REMEDY not in out
    assert "feedback.drafts:   quiet" in out


def test_stage_16_enabled_prints_neither_remedy(tmp_path):
    out = _probe_stage_16(_project(tmp_path, feedback=True), on_path=True)
    assert "feedback.enabled:  true" in out
    assert _ABSENT_REMEDY not in out
    assert _DISABLED_REMEDY not in out


def test_stage_16_enabled_never_reads_the_raw_config(tmp_path):
    config = _project(tmp_path, feedback=True)
    with mock.patch.object(dp, "_posting_state", side_effect=AssertionError("read")) as probe:
        _probe_stage_16(config, on_path=True)
    probe.assert_not_called()


def test_stage_16_absent_key_never_writes_config_yaml(tmp_path):
    config = _project(tmp_path)
    path = Path(config["_planwise_root"]) / "config.yaml"
    before = path.read_bytes()
    _probe_stage_16(config, on_path=True)
    assert path.read_bytes() == before


def _reload_with(config, text):
    path = Path(config["_planwise_root"]) / "config.yaml"
    path.write_text(text, encoding="utf-8")
    return config_loader.load_config(config_path=path)


def test_stage_16_a_feedback_key_that_is_not_a_block_keeps_the_disabled_remedy(tmp_path):
    config = _reload_with(_project(tmp_path), "feedback: {enabled: false}\n")
    out = _probe_stage_16(config, on_path=True)
    assert "feedback.enabled:  false (could not tell an absent key from a set one: " in out
    assert "block mapping" in out
    assert _DISABLED_REMEDY in out
    assert _ABSENT_REMEDY not in out


def test_stage_16_a_helper_import_failure_costs_only_the_distinction(tmp_path):
    # doctor_probes must not import the helper at module load.
    assert "feedback_drafts" not in vars(dp)
    with mock.patch.dict(sys.modules, {"feedback_drafts": None}):
        out = _probe_stage_16(_project(tmp_path), on_path=True)
    assert "feedback.enabled:  false (could not tell an absent key from a set one: " in out
    assert _DISABLED_REMEDY in out
    assert "gh resolvable:     yes" in out


def test_stage_16_a_missing_config_file_costs_only_the_distinction(tmp_path):
    config = _project(tmp_path)
    (Path(config["_planwise_root"]) / "config.yaml").unlink()
    out = _probe_stage_16(config, on_path=True)
    assert "feedback.enabled:  false (could not tell an absent key from a set one: " in out
    assert _DISABLED_REMEDY in out


@pytest.mark.parametrize(
    ("text", "line"),
    [
        ("feedback:\n  enabled: false\n", "feedback.enabled:  false"),
        ("feedback:\n  enabled: no\n", "feedback.enabled:  false"),
        ("feedback:\n  enabled:\n", _ABSENT_LINE),
        ("feedback:\n  repo: gabgoss/planwise\n", _ABSENT_LINE),
        ("project:\n  name: Fixture\n", _ABSENT_LINE),
    ],
)
def test_stage_16_line_follows_the_engine_posting_state(tmp_path, text, line):
    config = _reload_with(_project(tmp_path), text)
    state = fd.read_posting_state(Path(config["_planwise_root"]) / "config.yaml")
    out = _probe_stage_16(config, on_path=True)
    assert line in out
    assert (state == "absent") == (_ABSENT_LINE in out)


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


_REMEDY_HINT = (
    "review them with /planwise feedback --drafts, or post one with /planwise feedback --post <draftId>"
)


def _write_draft(directory, name, *, status="queued", drafted_by="model", age_days=1, created_at=None):
    """One draft file. `age_days` sets `created_at` that many days in the past,
    unless `created_at` gives the moment itself."""
    created = (created_at or datetime.now(timezone.utc) - timedelta(days=age_days)).isoformat()
    text = (
        "---\n"
        f"draft_id: {name[:-3]}\n"
        f"created_at: {created}\n"
        f"drafted_by: {drafted_by}\n"
        "kind: bug\n"
        f"title: {name}\n"
        f"status: {status}\n"
        "---\n"
        "Body.\n"
    )
    (directory / name).write_text(text, encoding="utf-8")


def _queue_fixture(tmp_path, queued, *, feedback=None):
    """A feedback directory holding `queued` queued model drafts plus four
    files that must not count: a hand-written draft, a discarded model draft,
    a non-matching name and an expired-by-age model draft."""
    config = _project(tmp_path, feedback=feedback)
    directory = Path(config["_feedback_dir"])
    directory.mkdir()
    for index in range(queued):
        _write_draft(directory, f"2026-01-{index + 1:02d}-draft-bug-queued-{index}.md")
    _write_draft(directory, "2026-02-01-draft-bug-hand.md", drafted_by="user")
    _write_draft(directory, "2026-02-02-draft-bug-gone.md", status="discarded")
    _write_draft(directory, "notes.md")
    _write_draft(directory, "2026-02-03-draft-bug-old.md", age_days=fd.EXPIRY_DAYS + 10)
    return config


def _tree_bytes(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def test_stage_17_counts_only_queued_model_drafts(tmp_path):
    out = _run(dp._stage_17, _queue_fixture(tmp_path, 3))
    assert "model drafts queued: 3" in out
    assert _REMEDY_HINT in out


def test_stage_17_zero_queued_prints_no_hint(tmp_path):
    out = _run(dp._stage_17, _queue_fixture(tmp_path, 0))
    assert "model drafts queued: 0" in out
    assert "feedback --post" not in out


def test_stage_17_absent_directory_is_not_checked(tmp_path):
    out = _run(dp._stage_17, _project(tmp_path))
    assert "model drafts queued: not checked" in out
    assert "feedback --post" not in out


def test_stage_17_unreadable_config_is_not_checked(tmp_path):
    buf = io.StringIO()
    with (
        mock.patch.object(dp, "_load_project_config", return_value=(None, "no config.yaml")),
        contextlib.redirect_stdout(buf),
    ):
        dp.run_probes(object())
    out = buf.getvalue()
    assert "model drafts queued: not checked" in out
    assert out.count("model drafts queued:") == 1  # only the Stage 17 row carries the line
    assert "model-draft .gitignore line: not checked" in out
    assert "feedback --post" not in out


def test_stage_17_is_read_only_and_does_not_expire_an_old_draft(tmp_path):
    config = _queue_fixture(tmp_path, 2)
    directory = Path(config["_feedback_dir"])
    before = _tree_bytes(directory)
    # The aged draft is still `queued` on disk: a writer would flip it to `expired`.
    assert b"status: queued" in before["2026-02-03-draft-bug-old.md"]
    out = _run(dp._stage_17, config)
    assert _tree_bytes(directory) == before
    assert "model drafts queued: 2" in out


def test_stage_17_counts_ten_or_more_queued_drafts(tmp_path):
    # Two-digit day names must still match the helper's draft-name pattern.
    out = _run(dp._stage_17, _queue_fixture(tmp_path, 10))
    assert "model drafts queued: 10" in out


def test_stage_17_a_failed_count_keeps_the_presence_lines(tmp_path):
    config = _queue_fixture(tmp_path, 1)
    with mock.patch.object(fd, "count_queued", side_effect=OSError("draft unreadable")):
        out = _run(dp._stage_17, config)
    assert "exists:               yes" in out
    assert "— present." in out
    assert "model drafts queued: not checked (the count failed: draft unreadable)" in out
    assert "feedback --post" not in out


def test_stage_17_a_helper_import_failure_stays_inside_stage_17(tmp_path):
    # doctor_probes must not import the helper at module load.
    assert "feedback_drafts" not in vars(dp)
    config = _queue_fixture(tmp_path, 1)
    with mock.patch.dict(sys.modules, {"feedback_drafts": None}):
        out = _run(dp._stage_17, config)
    assert "exists:               yes" in out
    assert "model drafts queued: not checked (the count failed:" in out


def test_stage_17_count_matches_the_helper_list_at_the_expiry_boundary(tmp_path):
    now = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
    config = _project(tmp_path)
    directory = Path(config["_feedback_dir"])
    directory.mkdir()
    limit = timedelta(days=fd.EXPIRY_DAYS)
    _write_draft(directory, "2026-01-01-draft-bug-at-limit.md", created_at=now - limit)
    _write_draft(directory, "2026-01-02-draft-bug-past-limit.md", created_at=now - limit - timedelta(seconds=1))
    buf = io.StringIO()
    with mock.patch.object(fd, "_now", return_value=now):
        out = _run(dp._stage_17, config)
        with contextlib.redirect_stdout(buf):
            assert fd.main(["list", "--json", "--feedback-dir", str(directory)]) == 0
    listed = [item for item in json.loads(buf.getvalue()) if item["status"] == "queued"]
    assert [item["path"] for item in listed] == ["2026-01-01-draft-bug-at-limit.md"]
    assert f"model drafts queued: {len(listed)}" in out


# --- Stage 17: the model-draft .gitignore line -------------------------------

_IGNORE_ROW = "model-draft .gitignore line:"
_IGNORE_REMEDY = "! .gitignore has no model-draft ignore line"


def _gitignore(config):
    return Path(config["_project_root"]) / ".gitignore"


def _expected_ignore_line(config):
    """The line init writes, built from the fixture's own layout: the project
    root holds `planwise/`, and the feedback directory sits inside it."""
    return ge.model_draft_line("planwise", Path(config["_feedback_dir"]).name)


def test_stage_17_reports_an_absent_ignore_line_and_names_the_fix(tmp_path):
    config = _project(tmp_path)
    out = _run(dp._stage_17, config)
    assert f"{_IGNORE_ROW} absent" in out
    assert _IGNORE_REMEDY in out
    assert "/planwise init or /planwise upgrade (both add it)" in out
    assert _expected_ignore_line(config) in out


def test_stage_17_reports_a_present_ignore_line_without_a_remedy(tmp_path):
    config = _project(tmp_path)
    _gitignore(config).write_bytes(b"dist/\r\n" + _expected_ignore_line(config).encode() + b"  \r\n")
    out = _run(dp._stage_17, config)
    assert f"{_IGNORE_ROW} present" in out
    assert _IGNORE_REMEDY not in out


def test_stage_17_reports_a_negated_ignore_line_as_an_opt_out(tmp_path):
    config = _project(tmp_path)
    _gitignore(config).write_bytes(b"!" + _expected_ignore_line(config).encode() + b"\n")
    out = _run(dp._stage_17, config)
    assert f"{_IGNORE_ROW} opted out" in out
    assert _IGNORE_REMEDY not in out


def test_stage_17_ignore_check_never_writes(tmp_path):
    config = _project(tmp_path)
    project_root = Path(config["_project_root"])
    before = _tree_bytes(project_root)
    _run(dp._stage_17, config)
    assert not _gitignore(config).exists()  # a missing file stays missing
    assert _tree_bytes(project_root) == before
    original = b"dist/\n*.log"  # no trailing newline: a writer would append one
    _gitignore(config).write_bytes(original)
    _run(dp._stage_17, config)
    assert _gitignore(config).read_bytes() == original


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"dist/\n",
        b"{line}\n",
        b"{line}  \r\n",
        b"!{line}\n",
        b"{line}\n!{line}\n",
        b"!{line}\n{line}\n",
        b"{line}-extra\n",
        b"# {line}\n",
    ],
)
def test_stage_17_and_the_writer_agree_on_what_counts_as_present(tmp_path, content):
    config = _project(tmp_path)
    line = _expected_ignore_line(config)
    data = content.replace(b"{line}", line.encode())
    _gitignore(config).write_bytes(data)
    out = _run(dp._stage_17, config)
    twin = tmp_path / "twin.gitignore"
    twin.write_bytes(data)
    would_write = ge.ensure_line(twin, line)
    assert (f"{_IGNORE_ROW} absent" in out) == would_write
    assert (_IGNORE_REMEDY in out) == would_write


def test_stage_17_an_unreadable_gitignore_keeps_the_other_lines(tmp_path):
    config = _queue_fixture(tmp_path, 2)
    _gitignore(config).mkdir()  # reading a directory as a file raises
    out = _run(dp._stage_17, config)
    assert f"{_IGNORE_ROW} not checked (the check failed:" in out
    assert _IGNORE_REMEDY not in out
    assert "exists:               yes" in out
    assert "model drafts queued: 2" in out


def test_stage_17_a_gitignore_helper_import_failure_stays_inside_stage_17(tmp_path):
    # doctor_probes must not import the helper at module load.
    assert "gitignore_entry" not in vars(dp)
    config = _queue_fixture(tmp_path, 1)
    with mock.patch.dict(sys.modules, {"gitignore_entry": None}):
        out = _run(dp._stage_17, config)
    assert f"{_IGNORE_ROW} not checked (the check failed:" in out
    assert "model drafts queued: 1" in out


def test_stage_17_an_inexpressible_feedback_dir_is_not_checked(tmp_path):
    config = _project(tmp_path)
    config["_feedback_dir"] = Path(config["_planwise_root"]) / "Feed[back]"  # a glob character
    out = _run(dp._stage_17, config)
    assert f"{_IGNORE_ROW} not checked (the check failed:" in out
    assert _IGNORE_REMEDY not in out


# --- Stage 17: the posting-off note ------------------------------------------

_POSTING_OFF = "Posting is off (feedback.enabled is false)"


def test_stage_17_prints_the_posting_off_note_when_drafts_queue_and_posting_is_off(tmp_path):
    out = _run(dp._stage_17, _queue_fixture(tmp_path, 3, feedback=False))
    assert _REMEDY_HINT in out
    assert _POSTING_OFF in out
    assert "Choosing Review and post sets it to true in config.yaml" in out


def test_stage_17_prints_the_posting_off_note_when_the_key_is_absent(tmp_path):
    # An absent key reads as false, the loader's default.
    assert _POSTING_OFF in _run(dp._stage_17, _queue_fixture(tmp_path, 1))


def test_stage_17_omits_the_posting_off_note_when_posting_is_on(tmp_path):
    out = _run(dp._stage_17, _queue_fixture(tmp_path, 3, feedback=True))
    assert _REMEDY_HINT in out
    assert _POSTING_OFF not in out


def test_stage_17_omits_the_posting_off_note_when_nothing_is_queued(tmp_path):
    out = _run(dp._stage_17, _queue_fixture(tmp_path, 0, feedback=False))
    assert "model drafts queued: 0" in out
    assert _POSTING_OFF not in out


def test_stage_17_omits_the_posting_off_note_when_the_count_failed(tmp_path):
    config = _queue_fixture(tmp_path, 1, feedback=False)
    with mock.patch.object(fd, "count_queued", side_effect=OSError("draft unreadable")):
        out = _run(dp._stage_17, config)
    assert _POSTING_OFF not in out


def test_stage_17_omits_the_posting_off_note_when_the_directory_is_absent(tmp_path):
    out = _run(dp._stage_17, _project(tmp_path, feedback=False))
    assert _POSTING_OFF not in out


def test_stage_17_posting_off_note_does_not_write(tmp_path):
    config = _queue_fixture(tmp_path, 2, feedback=False)
    config_file = Path(config["_planwise_root"]) / "config.yaml"
    before = config_file.read_bytes()
    _run(dp._stage_17, config)
    assert config_file.read_bytes() == before  # the note describes the change and makes none


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
