"""Unit tests for migrate_backlog_repairs.py, the pure-function helpers a
backlog-index migrator's repair flags call.

Every function under test either transforms a string or maps a set of paths
to values -- none of them write a file or read an index -- so every test
here works on in-memory text or, for `created_dates` alone, a throwaway git
repository under `tmp_path`. Byte-exact round-trip assertions compare
`.encode("utf-8")` output directly, never `git diff`, and any fixture file
written to disk uses `write_bytes` rather than `write_text` so a platform
newline translation can never cancel out the property under test.

Run with:  python -m pytest tests/test_migrate_backlog_repairs.py -q
"""

import re
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

# Allow imports whether pytest is launched from the repo root or scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import migrate_backlog_support as sup  # noqa: E402
from frontmatter_parser import BOM_CHAR  # noqa: E402
from migrate_backlog_repairs import (  # noqa: E402
    created_dates,
    dependency_bullets,
    filename_fields,
    first_id_in,
    insert_missing_keys,
    partial_frontmatter,
    render_frontmatter,
    replace_key_line,
    title_from_cell,
)


def _split(text: str, marker: str) -> tuple:
    """Split `text` at the first occurrence of `marker`, marker included in
    the second half -- so `before + <anything> + after` can be compared to
    a function's actual output for an exact prefix/suffix byte check."""
    idx = text.index(marker)
    return text[:idx], text[idx:]


# --- render_frontmatter -----------------------------------------------------

def test_render_frontmatter_lf():
    fields = {
        "id": "003", "title": 'Sample title with "quotes"', "priority": "High",
        "status": "NOT_STARTED", "abbrev": "SMP", "created": "2024-01-01",
        "blocks": ["001", "005"],
    }
    result = render_frontmatter(fields, "\n")
    assert result == (
        "---\n"
        "id: 003\n"
        'title: "Sample title with \\"quotes\\""\n'
        "priority: High\n"
        "status: NOT_STARTED\n"
        "abbrev: SMP\n"
        "created: 2024-01-01\n"
        "blocks: [001, 005]\n"
        "---\n"
        "\n"
    )


def test_render_frontmatter_crlf_empty_blocks():
    fields = {
        "id": "007", "title": "Plain title", "priority": "Low",
        "status": "IN_PROGRESS", "abbrev": "INF", "created": "2024-02-02",
        "blocks": [],
    }
    result = render_frontmatter(fields, "\r\n")
    assert result == (
        "---\r\n"
        "id: 007\r\n"
        'title: "Plain title"\r\n'
        "priority: Low\r\n"
        "status: IN_PROGRESS\r\n"
        "abbrev: INF\r\n"
        "created: 2024-02-02\r\n"
        "blocks: []\r\n"
        "---\r\n"
        "\r\n"
    )


# --- insert_missing_keys -----------------------------------------------------

_EXISTING_LF = (
    "---\n"
    "id: 003\n"
    'title: "Sample"\n'
    "priority: High\n"
    "status: NOT_STARTED\n"
    "abbrev: SMP\n"
    "---\n"
    "\n"
    "Body text\n"
)
_MISSING = {"created": "2024-01-01", "blocks": "[001]"}


def test_insert_missing_keys_preserves_lf_bytes_around_insertion():
    before, after = _split(_EXISTING_LF, "---\n\nBody text\n")
    result = insert_missing_keys(_EXISTING_LF, _MISSING, "\n")
    inserted = "created: 2024-01-01\nblocks: [001]\n"
    assert result == before + inserted + after
    result_bytes = result.encode("utf-8")
    assert result_bytes[: len(before.encode("utf-8"))] == before.encode("utf-8")
    assert result_bytes[-len(after.encode("utf-8")):] == after.encode("utf-8")


def test_insert_missing_keys_preserves_crlf_bytes_around_insertion():
    existing_crlf = _EXISTING_LF.replace("\n", "\r\n")
    before, after = _split(existing_crlf, "---\r\n\r\nBody text\r\n")
    result = insert_missing_keys(existing_crlf, _MISSING, "\r\n")
    inserted = "created: 2024-01-01\r\nblocks: [001]\r\n"
    assert result == before + inserted + after
    result_bytes = result.encode("utf-8")
    assert result_bytes[: len(before.encode("utf-8"))] == before.encode("utf-8")
    assert result_bytes[-len(after.encode("utf-8")):] == after.encode("utf-8")


def test_insert_missing_keys_preserves_bom_and_crlf():
    existing_crlf = _EXISTING_LF.replace("\n", "\r\n")
    bommed = BOM_CHAR + existing_crlf
    before, after = _split(bommed, "---\r\n\r\nBody text\r\n")
    result = insert_missing_keys(bommed, _MISSING, "\r\n")
    inserted = "created: 2024-01-01\r\nblocks: [001]\r\n"
    assert result.startswith(BOM_CHAR)
    assert result == before + inserted + after
    result_bytes = result.encode("utf-8")
    assert result_bytes[: len(before.encode("utf-8"))] == before.encode("utf-8")
    assert result_bytes[-len(after.encode("utf-8")):] == after.encode("utf-8")


def test_insert_missing_keys_raises_without_closing_fence():
    with pytest.raises(ValueError):
        insert_missing_keys("---\nid: 003\nno closing fence\n", _MISSING, "\n")


# --- replace_key_line --------------------------------------------------------

def test_replace_key_line_rewrites_scalar_value():
    text = "---\nid: 003\nstatus: NOT_STARTED\nabbrev: SMP\n---\n\nBody\n"
    result = replace_key_line(text, "status", "IN_PROGRESS")
    assert result == "---\nid: 003\nstatus: IN_PROGRESS\nabbrev: SMP\n---\n\nBody\n"
    prefix, suffix = "---\nid: 003\n", "\nabbrev: SMP\n---\n\nBody\n"
    result_bytes = result.encode("utf-8")
    assert result_bytes[: len(prefix.encode("utf-8"))] == prefix.encode("utf-8")
    assert result_bytes[-len(suffix.encode("utf-8")):] == suffix.encode("utf-8")


def test_replace_key_line_rewrites_block_form_blocks_to_flow_form():
    text = "---\nid: 003\nblocks:\n  - 001\n  - 005\n---\n\nBody\n"
    result = replace_key_line(text, "blocks", "[001, 005, 009]")
    assert result == "---\nid: 003\nblocks: [001, 005, 009]\n---\n\nBody\n"


def test_replace_key_line_raises_keyerror_when_key_absent():
    text = "---\nid: 003\nstatus: NOT_STARTED\n---\n\nBody\n"
    with pytest.raises(KeyError):
        replace_key_line(text, "priority", "High")


def test_replace_key_line_raises_keyerror_without_frontmatter():
    with pytest.raises(KeyError):
        replace_key_line("# Just a body\n", "status", "IN_PROGRESS")


# --- partial_frontmatter ------------------------------------------------------

def test_partial_frontmatter_no_opening_fence():
    raw_map, has_block, bom, nl = partial_frontmatter("# Just a body\n")
    assert raw_map is None
    assert has_block is False
    assert bom == ""
    assert nl == "\n"


def test_partial_frontmatter_unterminated_block():
    raw_map, has_block, bom, nl = partial_frontmatter("---\nid: 003\nno closing fence\n")
    assert raw_map is None
    assert has_block is True
    assert bom == ""
    assert nl == "\n"


def test_partial_frontmatter_bom_crlf_well_formed():
    text = BOM_CHAR + "---\r\nid: 003\r\nstatus: NOT_STARTED\r\n---\r\n\r\nBody\r\n"
    raw_map, has_block, bom, nl = partial_frontmatter(text)
    assert raw_map == {"id": "003", "status": "NOT_STARTED"}
    assert has_block is True
    assert bom == BOM_CHAR
    assert nl == "\r\n"


# --- title_from_cell -----------------------------------------------------------

def test_title_from_cell_strips_markdown_and_truncates_at_120():
    filler = "delta " * 30  # 180 chars, pushes the cell well past 120
    cell = f"**Alpha** bravo [charlie](notes.md) {filler}"
    result = title_from_cell(cell)
    assert "*" not in result
    assert "[" not in result
    assert len(result) <= 120
    assert result.startswith("Alpha bravo charlie")
    assert not result.endswith(" ")
    full_plain = sup.plain(cell)
    assert len(full_plain) > 120
    assert result == full_plain[: len(result)]


# --- filename_fields -----------------------------------------------------------

def test_filename_fields_three_digit_id_with_part_suffix():
    assert filename_fields("ITEM-042-01-DOC-Topic.md") == ("042", "DOC")


def test_filename_fields_four_digit_id_no_part_suffix():
    assert filename_fields("X-1234-INFRA-T.md") == ("1234", "INFRA")


def test_filename_fields_non_matching_name_returns_none():
    assert filename_fields("notes.md") is None


# --- created_dates ---------------------------------------------------------------

def _git_init_commit(root):
    subprocess.run(["git", "init", "-q"], cwd=str(root), check=True)
    subprocess.run(["git", "add", "-A"], cwd=str(root), check=True)
    subprocess.run(["git", "-c", "user.email=t@example.com", "-c", "user.name=t",
                    "commit", "-q", "-m", "init"], cwd=str(root), check=True)


def _git_commit(root, message):
    subprocess.run(["git", "add", "-A"], cwd=str(root), check=True)
    subprocess.run(["git", "-c", "user.email=t@example.com", "-c", "user.name=t",
                    "commit", "-q", "-m", message], cwd=str(root), check=True)


def test_created_dates_git_git_follow_and_mtime(tmp_path):
    root = tmp_path / "proj"
    backlog = root / "Backlog"
    backlog.mkdir(parents=True)

    plain_file = backlog / "001-Plain.md"
    plain_file.write_bytes(b"a plain committed item, never moved\n")
    renamed_file = backlog / "002-Renamed.md"
    renamed_file.write_bytes(b"an item later moved into Archive\n")
    _git_init_commit(root)

    archive = backlog / "Archive"
    archive.mkdir()
    subprocess.run(
        ["git", "mv", "Backlog/002-Renamed.md", "Backlog/Archive/002-Renamed.md"],
        cwd=str(root), check=True,
    )
    _git_commit(root, "move to archive")
    moved_file = archive / "002-Renamed.md"

    untracked_file = backlog / "003-Untracked.md"
    untracked_file.write_bytes(b"never added to git\n")

    result = created_dates(root, [plain_file, moved_file, untracked_file], backlog)

    plain_date, plain_source = result[plain_file]
    assert plain_source == "git"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", plain_date)

    moved_date, moved_source = result[moved_file]
    assert moved_source == "git-follow"
    assert moved_date == plain_date  # both added in the same initial commit

    untracked_date, untracked_source = result[untracked_file]
    assert untracked_source == "mtime"
    expected = date.fromtimestamp(untracked_file.stat().st_mtime).isoformat()
    assert untracked_date == expected


def test_created_dates_mtime_when_not_a_repository(tmp_path):
    backlog = tmp_path / "Backlog"
    backlog.mkdir()
    lone_file = backlog / "001-Lone.md"
    lone_file.write_bytes(b"no git repository here at all\n")

    result = created_dates(tmp_path, [lone_file], backlog)

    lone_date, lone_source = result[lone_file]
    assert lone_source == "mtime"
    expected = date.fromtimestamp(lone_file.stat().st_mtime).isoformat()
    assert lone_date == expected


# --- dependency_bullets ---------------------------------------------------------

def test_dependency_bullets_heading_two_bullets_one_continuation_one_no_id():
    lines = [
        "**Soft dependencies**",
        "- 003 relates to 001 (shared parser)",
        "  continues describing the shared parser here",
        "- a bullet naming no identifier at all",
    ]
    result = dependency_bullets(lines)
    assert len(result) == 2

    line_no, owner, text = result[0]
    assert line_no == 1
    assert owner == "003"
    assert text == (
        "- 003 relates to 001 (shared parser)\n"
        "  continues describing the shared parser here"
    )

    line_no2, owner2, text2 = result[1]
    assert line_no2 == 3
    assert owner2 is None
    assert text2 == "- a bullet naming no identifier at all"


# --- first_id_in -----------------------------------------------------------------

def test_first_id_in_ordering_versus_ids_in():
    text = "See step 2 before item 010, and also 004 for context."
    assert first_id_in(text) == "010"
    assert sup.ids_in(text) == ["002", "004", "010"]


def test_first_id_in_returns_none_with_no_qualifying_id():
    assert first_id_in("See step 2 and item 5, nothing else.") is None


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
