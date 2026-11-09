"""Tests for scan_runner_disclosures.py."""
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import pytest
import scan_runner_disclosures as srd

CLEAN = "TASK_STATUS: COMPLETE\nOUTPUT_FILES: a.py\nISSUES: none\n"


def _run(tmp_path, text):
    path = tmp_path / "return.txt"
    path.write_text(text, encoding="utf-8")
    return srd.main([str(path)])


def test_clean_block_exits_zero(tmp_path, capsys):
    assert _run(tmp_path, CLEAN) == 0
    assert "clean" in capsys.readouterr().out


@pytest.mark.parametrize(
    "sentence,phrase_no",
    [
        ("I left the threshold unchanged to preserve the expected gate value.", 1),
        ("The count was achieved by trimming two rows so the gate would pass.", 2),
        ("i deviated from the spec to make the gate pass", 3),
    ],
)
def test_each_phrase_is_flagged(tmp_path, capsys, sentence, phrase_no):
    assert _run(tmp_path, CLEAN + sentence + "\n") == 1
    out = capsys.readouterr().out
    assert f"phrase {phrase_no}" in out
    assert "line 4" in out


def test_phrase_wrapped_across_spaces_is_flagged(tmp_path):
    assert _run(tmp_path, "I left  the  limit unchanged to preserve the expected gate value") == 1


def test_stdin_dash(monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO("I deviated from the spec to make the gate pass"))
    assert srd.main(["-"]) == 1


def test_usage_exit_two(capsys):
    assert srd.main([]) == 2
    assert srd.main(["a", "b"]) == 2
    assert srd.main(["/nonexistent/none.txt"]) == 2


@pytest.mark.parametrize("flag", ["--help", "-h"])
def test_help_flag_prints_usage_and_exits_zero(capsys, flag):
    assert srd.main([flag]) == 0
    captured = capsys.readouterr()
    assert "<file|->" in captured.out
    assert captured.err == ""


def test_reference_phrases_compile_to_wildcards():
    assert len(srd.PATTERNS) == 3
    assert srd.WILDCARD in srd.PATTERNS[0].pattern
    assert srd.PATTERNS[1].pattern.count(srd.WILDCARD) == 2
    assert srd.WILDCARD not in srd.PATTERNS[2].pattern


def test_non_utf8_message_exits_two(tmp_path, capsys):
    path = tmp_path / "return.txt"
    path.write_bytes("TASK_STATUS: COMPLETE\n".encode("utf-16"))
    assert srd.main([str(path)]) == 2
    assert capsys.readouterr().err.startswith("Error:")


def test_hard_wrapped_phrase_is_flagged_at_its_start_line(tmp_path, capsys):
    text = "TASK_STATUS: COMPLETE\nI deviated from the spec to make\nthe gate pass\n"
    assert _run(tmp_path, text) == 1
    assert "HIT line 2 phrase 3" in capsys.readouterr().out


def test_phrase_split_by_blank_line_is_clean(tmp_path):
    assert _run(tmp_path, "I deviated from the spec to make\n\nthe gate pass\n") == 0


def test_long_line_without_phrase_end_is_fast_and_clean(tmp_path):
    assert _run(tmp_path, "achieved by " + "x " * 20000 + "\n") == 0


DORMANT = "KEY_FINDINGS:\n- the hint stays dormant until a follow-up wires it\n"


def test_complete_with_dormant_claim_fires(tmp_path, capsys):
    assert _run(tmp_path, CLEAN + DORMANT) == 1
    out = capsys.readouterr().out
    assert "DORMANT line 5" in out
    assert "clean: 0 disclosure phrases" in out


def test_same_text_under_partial_is_clean(tmp_path):
    assert _run(tmp_path, CLEAN.replace("COMPLETE", "PARTIAL") + DORMANT) == 0


@pytest.mark.parametrize(
    "sentence",
    [
        "- no follow-up needed",
        "- follow-up: none",
        "- nothing is dormant",
        "- the flag is wired at scripts/x.py:12",
    ],
)
def test_complete_with_honest_wording_is_clean(tmp_path, sentence):
    assert _run(tmp_path, CLEAN + sentence + "\n") == 0


@pytest.mark.parametrize(
    "sentence",
    ["- the flag is not yet wired", "- a follow-up is required to register it", "- both helpers remain dormant"],
)
def test_each_dormant_shape_fires_under_complete(tmp_path, sentence):
    assert _run(tmp_path, CLEAN + sentence + "\n") == 1


def test_status_must_be_on_its_own_line(tmp_path):
    text = "Note: TASK_STATUS: COMPLETE was wrong.\nTASK_STATUS: PARTIAL\n" + DORMANT
    assert _run(tmp_path, text) == 0


def test_disclosure_phrases_unchanged():
    assert srd.PHRASES == (
        "I left X unchanged to preserve the expected gate value",
        "achieved by … so the gate would …",
        "I deviated from the spec to make the gate pass",
    )
