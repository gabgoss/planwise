#!/usr/bin/env python3
"""Tests for the raw-key state predicate and the splice-backed feedback writer.

`drafts_key_state` tells `no-block`, `absent` and `set` apart on the parsed
mapping, which the loader's defaulting cannot. `_apply_feedback_keys` backfills
a missing `feedback.drafts` and honours the two writer flags, one row of the
backfill rule per test below. Fixtures are built as bytes so line endings are
exact.
"""
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import config_gen
from config_gen import InitConfig, _apply_feedback_keys, drafts_key_state

SCRIPTS = Path(config_gen.__file__).resolve().parent

HEAD = b'plugin_version: "1.0.0"\n# keep this comment\n'
BLOCK_ABSENT = b'feedback:\n  enabled: false\n  repo: "gabgoss/planwise"\n'
BLOCK_SET = b'feedback:\n  enabled: false\n  repo: "gabgoss/planwise"\n  drafts: notify\n'
TAIL = b"style:\n  plain: true\n"


def _write(tmp_path, body: bytes) -> Path:
    path = tmp_path / "config.yaml"
    path.write_bytes(body)
    return path


def _state(path: Path) -> str:
    return drafts_key_state(yaml.safe_load(path.read_bytes()))


def _run(path, drafts=None, enabled=False, real_upgrade=False, state=None):
    return _apply_feedback_keys(
        path, state or _state(path), drafts, enabled,
        planwise_root="planwise", feedback_dir="Feedback", plugin_root=Path("/plug"),
        real_upgrade=real_upgrade)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_state_predicate_reads_the_three_shapes():
    assert drafts_key_state({"plugin_version": "1"}) == "no-block"
    assert drafts_key_state({"feedback": None}) == "no-block"
    assert drafts_key_state({"feedback": {"enabled": False}}) == "absent"
    assert drafts_key_state({"feedback": {"drafts": "notify"}}) == "set"


def test_state_predicate_counts_a_yaml_boolean_as_set():
    parsed = yaml.safe_load(b"feedback:\n  drafts: off\n")
    assert parsed["feedback"]["drafts"] is False
    assert drafts_key_state(parsed) == "set"


def test_set_without_flags_writes_nothing(tmp_path):
    path = _write(tmp_path, HEAD + BLOCK_SET + TAIL)
    before = path.read_bytes()
    assert _run(path) == []
    assert path.read_bytes() == before


def test_set_with_flags_reports_old_to_new_and_no_banner(tmp_path):
    path = _write(tmp_path, HEAD + BLOCK_SET + TAIL)
    lines = _run(path, drafts="quiet", enabled=True)
    assert lines == ["feedback.drafts: notify -> quiet", "feedback.enabled: false -> true"]
    assert not any("Feedback drafting:" in line for line in lines)
    assert yaml.safe_load(_text(path))["feedback"] == {"enabled": True, "repo": "gabgoss/planwise", "drafts": "quiet"}


def test_absent_without_flags_writes_notify_and_prints_the_banner(tmp_path):
    path = _write(tmp_path, HEAD + BLOCK_ABSENT + TAIL)
    lines = _run(path)
    assert len(lines) == 1
    assert lines[0].startswith("Feedback drafting: ON")
    assert "feedback.drafts: notify (default, no answer given); feedback.enabled: unchanged" in lines[0]
    assert "under planwise/Feedback/" in lines[0]
    assert 'python "/plug/scripts/feedback_drafts.py" disable-drafts --config "planwise/config.yaml"' in lines[0]
    assert yaml.safe_load(_text(path))["feedback"]["drafts"] == "notify"
    assert "# keep this comment" in _text(path)


def test_absent_with_drafts_flag_writes_only_the_flagged_value(tmp_path):
    path = _write(tmp_path, HEAD + BLOCK_ABSENT + TAIL)
    lines = _run(path, drafts="off", enabled=True)
    assert lines[0].startswith("Feedback drafting: OFF — Claude will not save local feedback drafts")
    assert "may now save" not in lines[0] and "disable-drafts" not in lines[0]
    assert "turn it on: set feedback.drafts: notify (or quiet) in planwise/config.yaml" in lines[0]
    assert "feedback.drafts: off (answered); feedback.enabled: true (set this run)" in lines[0]
    text = _text(path)
    assert text.count("drafts:") == 1
    assert yaml.safe_load(text)["feedback"]["drafts"] is False  # an unquoted `off` loads as a boolean
    assert "  drafts: off" in text
    assert yaml.safe_load(text)["feedback"]["enabled"] is True


def test_absent_with_only_the_enabled_flag_still_backfills_notify(tmp_path):
    path = _write(tmp_path, HEAD + BLOCK_ABSENT + TAIL)
    lines = _run(path, enabled=True)
    parsed = yaml.safe_load(_text(path))["feedback"]
    assert parsed["drafts"] == "notify"
    assert parsed["enabled"] is True
    assert "(default, no answer given); feedback.enabled: true (set this run)" in lines[0]


def test_no_block_without_flags_on_the_current_pin_branch_changes_nothing(tmp_path):
    path = _write(tmp_path, HEAD + TAIL)
    before = path.read_bytes()
    assert _state(path) == "no-block"
    assert _run(path, real_upgrade=False) == []
    assert path.read_bytes() == before


def test_no_block_without_flags_on_the_real_upgrade_prints_the_banner_only(tmp_path):
    # migrate_config already added the template block, which carries drafts: notify.
    path = _write(tmp_path, HEAD + BLOCK_SET + TAIL)
    before = path.read_bytes()
    lines = _run(path, state="no-block", real_upgrade=True)
    assert len(lines) == 1
    assert lines[0].startswith("Feedback drafting: ON")
    assert "feedback.drafts: notify (default, no answer given)" in lines[0]
    assert path.read_bytes() == before


def test_no_block_with_flags_creates_the_block_and_prints_the_banner(tmp_path):
    path = _write(tmp_path, HEAD + TAIL)
    lines = _run(path, drafts="quiet", enabled=True)
    assert lines[0].startswith("Feedback drafting: ON")
    assert "feedback.drafts: quiet (answered); feedback.enabled: true (set this run)" in lines[0]
    assert yaml.safe_load(_text(path))["feedback"] == {"drafts": "quiet", "enabled": True}


def test_no_block_with_only_the_enabled_flag_backfills_notify_so_the_banner_prints_once(tmp_path):
    path = _write(tmp_path, HEAD + TAIL)
    lines = _run(path, enabled=True)
    assert len(lines) == 1 and lines[0].startswith("Feedback drafting: ON")
    assert yaml.safe_load(_text(path))["feedback"] == {"enabled": True, "drafts": "notify"}
    after_first = path.read_bytes()
    assert _state(path) == "set"
    assert _run(path) == []
    assert path.read_bytes() == after_first


def test_enabled_flag_on_an_already_true_key_reports_unchanged(tmp_path):
    path = _write(tmp_path, HEAD + b"feedback:\n  enabled: true\n" + TAIL)
    lines = _run(path, enabled=True)
    assert "feedback.enabled: unchanged" in lines[0]
    assert "set this run" not in lines[0]


def test_banner_value_follows_the_loader_normalization(tmp_path):
    # A quoted, upper-case OFF is off to the loader, so the banner must say OFF too.
    path = _write(tmp_path, HEAD + b'feedback:\n  enabled: false\n  drafts: "OFF"\n' + TAIL)
    lines = _run(path, state="no-block", real_upgrade=True)
    assert lines[0].startswith("Feedback drafting: OFF")
    assert "feedback.drafts: off (default, no answer given)" in lines[0]


def test_a_write_the_filesystem_rejects_warns_and_returns_no_lines(tmp_path, capsys, monkeypatch):
    path = _write(tmp_path, HEAD + BLOCK_ABSENT + TAIL)
    before = path.read_bytes()

    def locked(config_path, text):
        raise PermissionError(f"{config_path} is locked")

    monkeypatch.setattr(config_gen, "write_config_checked", locked)
    assert _run(path) == []
    assert path.read_bytes() == before
    err = capsys.readouterr().err.strip().splitlines()
    assert len(err) == 1 and err[0].startswith("Warning: feedback keys left unchanged: ")


def test_second_call_on_the_written_file_is_idempotent(tmp_path):
    path = _write(tmp_path, HEAD + BLOCK_ABSENT + TAIL)
    assert _run(path)
    after_first = path.read_bytes()
    assert _state(path) == "set"
    assert _run(path) == []
    assert path.read_bytes() == after_first


def test_enabled_true_is_never_flipped_off_and_the_flag_is_a_no_op_on_it(tmp_path):
    body = HEAD + b"feedback:\n  enabled: true\n" + TAIL
    path = _write(tmp_path, body)
    _run(path)
    assert yaml.safe_load(_text(path))["feedback"]["enabled"] is True
    on = _write(tmp_path, HEAD + b"feedback:\n  enabled: true\n  drafts: quiet\n" + TAIL)
    before = on.read_bytes()
    assert _run(on, enabled=True) == []
    assert on.read_bytes() == before


@pytest.mark.skipif(sys.platform != "win32", reason="the checked writer translates newlines per platform")
def test_crlf_fixture_keeps_crlf_on_every_line(tmp_path):
    body = (HEAD + BLOCK_ABSENT + TAIL).replace(b"\n", b"\r\n")
    path = _write(tmp_path, body)
    before = path.read_bytes().count(b"\r\n")
    assert _run(path)
    data = path.read_bytes()
    assert data.count(b"\r\n") == before + 1
    assert data.count(b"\n") == data.count(b"\r\n")


def test_refused_edit_on_a_scalar_feedback_key(tmp_path, capsys):
    path = _write(tmp_path, HEAD + b"feedback: nope\n" + TAIL)
    before = path.read_bytes()
    assert _run(path, drafts="quiet") == []
    assert path.read_bytes() == before
    err = capsys.readouterr().err.strip().splitlines()
    assert len(err) == 1 and err[0].startswith("Warning: feedback keys left unchanged: ")


def test_refused_edit_when_the_result_would_not_parse(tmp_path, capsys):
    path = _write(tmp_path, HEAD + b"feedback:\n  enabled: false\n  bad: [unclosed\n" + TAIL)
    before = path.read_bytes()
    assert _run(path, state="absent") == []
    assert path.read_bytes() == before
    err = capsys.readouterr().err.strip().splitlines()
    assert len(err) == 1 and err[0].startswith("Warning: feedback keys left unchanged: ")


def test_init_config_defaults_ignore_the_flags():
    cfg = InitConfig(project_name="p", project_root=Path("."), plugin_root=Path("."))
    assert cfg.feedback_drafts is None
    assert cfg.feedback_enabled is False


def test_parser_accepts_both_flags_and_rejects_a_bad_value(tmp_path):
    # A trailing --help stops at argparse after the flags are parsed, so no init work runs.
    script = str(SCRIPTS / "init_project.py")
    ok = subprocess.run(
        [sys.executable, "-B", script, "--name", "p", "--project-root", str(tmp_path),
         "--feedback-drafts", "quiet", "--feedback-enabled", "--help"],
        capture_output=True, text=True, check=False)
    assert ok.returncode == 0, ok.stderr
    assert "--feedback-drafts" in ok.stdout and "--feedback-enabled" in ok.stdout
    assert list(tmp_path.iterdir()) == []
    bad = subprocess.run(
        [sys.executable, "-B", script, "--name", "p", "--project-root", str(tmp_path),
         "--feedback-drafts", "loud"],
        capture_output=True, text=True, check=False)
    assert bad.returncode == 2
    assert "invalid choice" in bad.stderr
