"""Unit tests for migrate_lessons_repairs.py, the pure-function repair
helpers a lessons migrator's repair flags call.

Every function under test transforms a string or maps a set of values to a
plan -- none of them write a file -- so every test here works on in-memory
text. Any fixture written to disk uses `write_bytes` (never `write_text`,
which normalizes line endings to the platform default and would cancel out
the CRLF-preservation property this suite checks).

Run with:  python -m pytest tests/test_migrate_lessons_repairs.py -q
"""

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import migrate_backlog_repairs as backlog_repairs
from generate_lessons_index import _read_frontmatter_map, _strip_quotes
from migrate_lessons_repairs import (
    RepairRefused,
    append_index_note,
    backfill_plan,
    cell_units,
    insert_missing_keys,
    normalize_lone_cr,
    quote_title_if_needed,
    reconcile_status,
    repair_ledger_rows,
)

VALID_STATUSES = frozenset({"documented", "promoted", "applied", "rule", "orphaned"})


# --- backfill_plan -----------------------------------------------------------

def test_backfill_no_block_gains_every_key_h1_wins_title(tmp_path):
    text = "# LL-001-Domain: The Lesson Title\n\n## Context\n\nSome body text.\n"
    path = tmp_path / "LL-001-Domain-Fixture.md"
    path.write_bytes(text.encode("utf-8"))
    row = {
        "id": "LL-001", "title": "unused row title", "category": "anti-pattern",
        "severity": "high", "language": "python, yaml", "technology": "planwise-plugin",
        "domain": "PROC", "source": "TestSource", "status": "documented",
    }
    plan = backfill_plan(path, text, row, VALID_STATUSES, "2026-09-27")
    assert plan["id"] == ("LL-001", "filename")
    assert plan["title"] == ("The Lesson Title", "h1")
    assert plan["category"] == ("anti-pattern", "row")
    assert plan["severity"] == ("high", "row")
    assert plan["language"] == ("[python, yaml]", "row")
    assert plan["technology"] == ("[planwise-plugin]", "row")
    assert plan["domain"] == ("[PROC]", "row")
    assert plan["source"] == ("TestSource", "row")
    assert plan["status"] == ("documented", "row")
    assert plan["applied-as"] == ("null", "default")  # templates/lesson.md's own value
    assert plan["date"][1] == "mtime"  # no project_root/lessons_dir -> mtime, file exists


def test_backfill_partial_block_gains_only_missing_keys(tmp_path):
    text = (
        "---\nid: LL-002\ntitle: Existing title\nseverity: low\nlanguage: [python]\n"
        "technology: [x]\ndomain: [x]\nsource: s\nstatus: documented\n---\n\nbody\n"
    )
    path = tmp_path / "LL-002-Domain-Fixture.md"
    path.write_bytes(text.encode("utf-8"))
    row = {"id": "LL-002", "category": "process", "date": "2026-09-01"}
    plan = backfill_plan(path, text, row, VALID_STATUSES, "2026-09-27")
    assert set(plan) == {"category", "date", "applied-as"}
    assert plan["category"] == ("process", "row")
    assert plan["date"] == ("2026-09-01", "row-date")
    assert plan["applied-as"] == ("null", "default")


def test_backfill_id_disagreement_refuses(tmp_path):
    text = "# LL-001-Domain: Title\n\nbody\n"
    path = tmp_path / "LL-001-Domain-Fixture.md"
    path.write_bytes(text.encode("utf-8"))
    row = {"id": "LL-999", "category": "x", "severity": "low", "language": "x",
           "technology": "x", "domain": "x", "source": "x", "status": "documented"}
    with pytest.raises(RepairRefused, match="id disagreement"):
        backfill_plan(path, text, row, VALID_STATUSES, "2026-09-27")


def test_backfill_id_agreement_does_not_refuse(tmp_path):
    text = "# LL-001-Domain: Title\n\nbody\n"
    path = tmp_path / "LL-001-Domain-Fixture.md"
    path.write_bytes(text.encode("utf-8"))
    row = {"id": "LL-001", "category": "x", "severity": "low", "language": "x",
           "technology": "x", "domain": "x", "source": "x", "status": "documented"}
    plan = backfill_plan(path, text, row, VALID_STATUSES, "2026-09-27")
    assert plan["id"] == ("LL-001", "filename")


def test_backfill_no_block_and_no_row_refuses(tmp_path):
    text = "# LL-001-Domain: Title\n\nbody\n"
    path = tmp_path / "LL-001-Domain-Fixture.md"
    path.write_bytes(text.encode("utf-8"))
    with pytest.raises(RepairRefused, match="no frontmatter block and no index row"):
        backfill_plan(path, text, None, VALID_STATUSES, "2026-09-27")


def test_backfill_no_block_but_row_present_does_not_refuse(tmp_path):
    text = "# LL-001-Domain: Title\n\nbody\n"
    path = tmp_path / "LL-001-Domain-Fixture.md"
    path.write_bytes(text.encode("utf-8"))
    row = {"id": "LL-001", "category": "x", "severity": "low", "language": "x",
           "technology": "x", "domain": "x", "source": "x", "status": "documented"}
    plan = backfill_plan(path, text, row, VALID_STATUSES, "2026-09-27")
    assert plan["title"] == ("Title", "h1")


def test_backfill_unparseable_block_refuses(tmp_path):
    text = "---\nid: LL-001\ntitle: X\n\nbody with no closing fence\n"
    path = tmp_path / "LL-001-Domain-Fixture.md"
    path.write_bytes(text.encode("utf-8"))
    row = {"id": "LL-001", "category": "x"}
    with pytest.raises(RepairRefused, match="unparseable"):
        backfill_plan(path, text, row, VALID_STATUSES, "2026-09-27")


def test_backfill_parseable_block_does_not_refuse(tmp_path):
    text = (
        "---\nid: LL-001\ntitle: X\nseverity: low\nlanguage: [x]\ntechnology: [x]\n"
        "domain: [x]\nsource: s\nstatus: documented\n---\n\nbody\n"
    )
    path = tmp_path / "LL-001-Domain-Fixture.md"
    path.write_bytes(text.encode("utf-8"))
    plan = backfill_plan(path, text, {"category": "process"}, VALID_STATUSES, "2026-09-27")
    assert plan["category"] == ("process", "row")


def test_backfill_date_falls_back_git_then_mtime(tmp_path, monkeypatch):
    monkeypatch.setattr(backlog_repairs, "_run_git", lambda args, cwd: None)
    text = "# LL-001-Domain: Title\n\nbody\n"
    path = tmp_path / "LL-001-Domain-Fixture.md"
    path.write_bytes(text.encode("utf-8"))
    row = {"id": "LL-001", "category": "x", "severity": "low", "language": "x",
           "technology": "x", "domain": "x", "source": "TestSource", "status": "documented"}
    plan = backfill_plan(path, text, row, VALID_STATUSES, "2026-09-27",
                          project_root=tmp_path, lessons_dir=tmp_path)
    assert plan["date"][1] == "mtime"


def test_backfill_status_invalid_row_status_defaults_documented(tmp_path):
    text = "# LL-001-Domain: Title\n\nbody\n"
    path = tmp_path / "LL-001-Domain-Fixture.md"
    path.write_bytes(text.encode("utf-8"))
    row = {"id": "LL-001", "category": "x", "severity": "low", "language": "x",
           "technology": "x", "domain": "x", "source": "x", "status": "not-a-real-status"}
    plan = backfill_plan(path, text, row, VALID_STATUSES, "2026-09-27")
    assert plan["status"] == ("documented", "default")


# --- H1 title backfill: one test per H1 shape ---------------------------------
# The live corpus survey found `# LL-NNN-DOMAIN: Title` (the canonical form)
# and `# LL-NNN — Title`; `LL-NNN: `, `LL-NNN - ` and `LL-NNN-Title` are the
# other separators the strip must also handle. The title keeps every byte
# after the id, the optional domain token and one separator.

_H1_ROW = {"id": "LL-002", "category": "process", "severity": "low", "language": "x",
           "technology": "x", "domain": "PROC", "source": "x", "status": "documented"}


@pytest.mark.parametrize("h1,expected", [
    ("# LL-002-PROC: Fixture lesson two", "Fixture lesson two"),
    ("# LL-002 — An Idle Notification Is Not a Completion Signal",
     "An Idle Notification Is Not a Completion Signal"),
    ("# LL-002: Colon form: keeps its inner colon", "Colon form: keeps its inner colon"),
    ("# LL-002 - Spaced hyphen form", "Spaced hyphen form"),
    ("# LL-002-PROC — Domain then em dash", "Domain then em dash"),
    ("# LL-002-Backfilled Title", "Backfilled Title"),
])
@pytest.mark.parametrize("nl", ["\n", "\r\n"])
def test_backfill_h1_title_strips_id_domain_and_separator(tmp_path, h1, expected, nl):
    text = f"---{nl}id: LL-002{nl}severity: low{nl}---{nl}{nl}{h1}{nl}{nl}## Context{nl}{nl}body{nl}"
    path = tmp_path / "LL-002-PROC-Fixture.md"
    path.write_bytes(text.encode("utf-8"))
    plan = backfill_plan(path, text, _H1_ROW, VALID_STATUSES, "2026-09-27")
    assert plan["title"] == (expected, "h1")


# --- insert_missing_keys (lesson key order, NOT the backlog's) --------------

def test_insert_missing_keys_lesson_order(tmp_path):
    text = "---\nid: LL-001\ntitle: T\n---\n\nbody\n"
    missing = {"status": "documented", "date": "2026-09-27", "category": "anti-pattern"}
    result = insert_missing_keys(text, missing, "\n")
    assert result == (
        "---\nid: LL-001\ntitle: T\n"
        "date: 2026-09-27\ncategory: anti-pattern\nstatus: documented\n"
        "---\n\nbody\n"
    )


def test_insert_missing_keys_touches_no_existing_line():
    text = "---\nid: LL-001\ntitle: T\n---\n\nbody\n"
    result = insert_missing_keys(text, {"severity": "high"}, "\n")
    assert result.startswith("---\nid: LL-001\ntitle: T\n")
    assert "severity: high\n---\n\nbody\n" in result


def test_backfilled_applied_as_matches_the_shipped_lesson_template():
    template = (Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "templates"
                / "lesson.md").read_text(encoding="utf-8")
    shipped = re.search(r"^applied-as:[ \t]*(\S+)", template, re.MULTILINE).group(1)
    text = "---\nid: LL-001\ntitle: T\n---\n\nbody\n"
    plan = backfill_plan(Path("LL-001-X-Y.md"), text, {"id": "LL-001", "category": "x", "severity": "low",
                                                       "source": "s", "date": "2026-09-01"},
                         VALID_STATUSES, "2026-09-27")
    assert plan["applied-as"][0] == shipped


@pytest.mark.parametrize("nl", ["\n", "\r\n"])
@pytest.mark.parametrize("bom", ["", "﻿"])
def test_insert_missing_keys_creates_a_block_when_the_file_has_none(nl, bom):
    body = f"# LL-005-PROC: A Title{nl}{nl}Some body.{nl}"
    missing = {"status": "documented", "id": "LL-005", "title": "A Title"}
    result = insert_missing_keys(bom + body, missing, nl)
    assert result == (f"{bom}---{nl}id: LL-005{nl}title: A Title{nl}status: documented{nl}---{nl}{nl}"
                      + body)
    assert result.endswith(body)  # every original byte kept, after the new block
    fm = backlog_repairs.partial_frontmatter(result)
    assert fm[1] is True and fm[0]["id"] == "LL-005"


def test_insert_missing_keys_still_raises_on_an_unclosed_block():
    with pytest.raises(ValueError, match="no closing frontmatter fence"):
        insert_missing_keys("---\nid: LL-001\nbody with no closing fence\n", {"title": "T"}, "\n")


# --- quote_title_if_needed ----------------------------------------------------

def _fm_block(title_line: str) -> str:
    return (
        "---\nid: LL-001\n" + title_line + "\ncategory: x\nseverity: low\n"
        "language: [x]\ntechnology: [x]\ndomain: [x]\nsource: s\nstatus: documented\n"
        "---\n\nbody\n"
    )


def test_quote_title_hash_gets_quoted():
    text = _fm_block("title: A lesson about #hashes")
    result, changed = quote_title_if_needed(text)
    assert changed
    assert 'title: "A lesson about #hashes"' in result


def test_quote_title_already_quoted_untouched():
    text = _fm_block('title: "Already quoted #ok"')
    result, changed = quote_title_if_needed(text)
    assert not changed
    assert result == text


def test_quote_title_reader_returns_whole_value(tmp_path):
    text = _fm_block("title: A lesson about #hashes")
    quoted, changed = quote_title_if_needed(text)
    assert changed
    path = tmp_path / "LL-001-Domain-Fixture.md"
    path.write_bytes(quoted.encode("utf-8"))
    raw_map = _read_frontmatter_map(path)
    assert _strip_quotes(raw_map["title"]) == "A lesson about #hashes"


# --- reconcile_status ----------------------------------------------------------

def _status_text(status: str) -> str:
    return f"---\nid: LL-001\nstatus: {status}\n---\n\nbody\n"


def test_reconcile_status_index_wins_flips():
    text = _status_text("documented")
    result, changed, detail = reconcile_status(text, "promoted", "index-wins", VALID_STATUSES)
    assert changed
    assert "status: promoted" in result
    assert "documented" in detail and "promoted" in detail


def test_reconcile_status_frontmatter_wins_records():
    text = _status_text("documented")
    result, changed, detail = reconcile_status(text, "promoted", "frontmatter-wins", VALID_STATUSES)
    assert not changed
    assert result == text
    assert "documented" in detail and "promoted" in detail


def test_reconcile_status_none_mode_refuses_naming_both_flags():
    text = _status_text("documented")
    with pytest.raises(RepairRefused) as exc:
        reconcile_status(text, "promoted", None, VALID_STATUSES)
    assert "index-wins" in str(exc.value)
    assert "frontmatter-wins" in str(exc.value)


def test_reconcile_status_agreement_none_mode_does_not_refuse():
    text = _status_text("documented")
    result, changed, _detail = reconcile_status(text, "documented", None, VALID_STATUSES)
    assert not changed
    assert result == text


def test_reconcile_status_invalid_row_status_never_wins():
    text = _status_text("documented")
    result, changed, detail = reconcile_status(text, "bogus", "index-wins", VALID_STATUSES)
    assert not changed
    assert result == text
    assert "valid=False" in detail


# --- cell_units ----------------------------------------------------------------

def test_cell_units_three_sentences_drops_title_keeps_two():
    title = "The Lesson Title"
    cell = "The Lesson Title. Sentence one continued here. Sentence two done."
    units = cell_units(cell, title)
    assert units == ["Sentence one continued here.", "Sentence two done."]


def test_cell_units_only_title_yields_none():
    title = "The Lesson Title"
    cell = "The Lesson Title."
    assert cell_units(cell, title) == []


def test_cell_units_markdown_stripped_for_title_comparison():
    title = "The Lesson Title"
    cell = "**The Lesson Title**. This is extra info."
    units = cell_units(cell, title)
    assert units == ["This is extra info."]


def test_cell_units_lone_cr_becomes_space():
    title = "The Lesson Title"
    cell = "The Lesson Title. Sentence one\rcontinued here. Sentence two done."
    units = cell_units(cell, title)
    assert all("\r" not in u for u in units)
    assert "Sentence one continued here." in units


def test_normalize_lone_cr_direct():
    assert normalize_lone_cr("a\rb\r\nc") == "a b\r\nc"


# --- append_index_note ----------------------------------------------------------

def test_append_two_units_under_dated_heading():
    body = "# LL-001\n\n## Context\n\nSome context.\n"
    units = ["First appended sentence.", "Second appended sentence."]
    result, appended, skipped = append_index_note(body, units, "\n", "2026-09-27")
    assert appended == units
    assert skipped == []
    assert "## Index Note (migrated 2026-09-27)" in result
    assert result.endswith("Second appended sentence.\n")


def test_append_skips_exact_match_and_counts_it():
    body = "# LL-001\n\n## Context\n\nFirst appended sentence. Something else.\n"
    units = ["First appended sentence.", "New sentence not present."]
    result, appended, skipped = append_index_note(body, units, "\n", "2026-09-27")
    assert skipped == ["First appended sentence."]
    assert appended == ["New sentence not present."]
    assert result.count("First appended sentence.") == 1


def test_append_rerun_appends_nothing():
    body = "# LL-001\n\n## Context\n\nSome context.\n"
    units = ["First appended sentence.", "Second appended sentence."]
    once, _appended1, _skipped1 = append_index_note(body, units, "\n", "2026-09-27")
    twice, appended2, skipped2 = append_index_note(once, units, "\n", "2026-09-27")
    assert appended2 == []
    assert skipped2 == units
    assert twice == once


def test_append_leaves_frontmatter_bytes_identical():
    frontmatter = "---\nid: LL-001\ntitle: T\n---\n"
    body = "\n# LL-001\n\n## Context\n\nSome context.\n"
    text = frontmatter + body
    result, _appended, _skipped = append_index_note(text, ["A new sentence here."], "\n", "2026-09-27")
    assert result.startswith(frontmatter)


def test_append_crlf_file_stays_crlf():
    body = "# LL-001\r\n\r\n## Context\r\n\r\nSome context.\r\n"
    result, appended, _skipped = append_index_note(body, ["A new CRLF sentence."], "\r\n", "2026-09-27")
    assert appended == ["A new CRLF sentence."]
    assert re.search(r"(?<!\r)\n", result) is None


# --- repair_ledger_rows -----------------------------------------------------

def test_repair_ledger_rows_one_row_per_repair():
    records = [
        ("LL-001-Fixture.md", "quote-title", 'title: A #hash', 'title: "A #hash"', "row"),
    ]
    result = repair_ledger_rows(records)
    assert result == '| LL-001-Fixture.md | quote-title | title: A #hash | title: "A #hash" | row |'


def test_repair_ledger_rows_truncates_and_escapes():
    long_before = "x" * 100
    records = [("f.md", "backfill", long_before, "short|after", "git")]
    result = repair_ledger_rows(records)
    fields = result.split(" | ")
    assert fields[2] == "x" * 60
    assert fields[3] == "short\\|after"
