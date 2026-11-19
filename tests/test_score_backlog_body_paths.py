"""Tests for the scoped-rule warning in score_backlog.py's `--route --id` detail."""

import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import score_backlog as sb

WARNING = "scoped_rules warning:"


def _dest(path, role):
    return {"path": path, "role": role, "rules": [], "verdict": "none"}


def _block(source, roles):
    return {
        "verdict": "none",
        "source": source,
        "rules_scanned": 18,
        "owning_lessons": [],
        "inject_form": "paths",
        "rules_bytes": 0,
        "destinations": [_dest(f"dir/file{i}.md", role) for i, role in enumerate(roles)],
        "rules_to_inject": [],
    }


def _text(block):
    return "\n".join(sb._format_scoped_rules(block))


def test_body_source_with_every_destination_create_warns():
    out = _text(_block("body", ["CREATE", "CREATE"]))
    assert WARNING in out
    assert "rewrite them project-relative" in out


def test_warning_sits_before_the_rules_to_inject_line():
    lines = sb._format_scoped_rules(_block("body", ["CREATE"]))
    assert lines[-1].startswith("  rules_to_inject:")
    assert lines[-2].startswith("  " + WARNING)


def test_one_edit_destination_prints_no_warning():
    assert WARNING not in _text(_block("body", ["CREATE", "EDIT"]))


def test_files_touched_source_prints_no_warning():
    assert WARNING not in _text(_block("files-touched", ["CREATE", "CREATE"]))


def test_no_destinations_prints_no_warning():
    assert WARNING not in _text(_block("body", []))


def test_block_not_computed_prints_no_warning():
    assert sb._format_scoped_rules(None) == ["  scoped_rules:      (not computed)"]
