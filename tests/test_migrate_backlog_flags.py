"""Tests for the repair flags of migrate_backlog_index.py: each flag off (the
refusal keeps its old fragment and names the flag, nothing written) and on
(write, ledger section, CLEAN re-run, byte-identical tree), the header-only
changelog, the read-only --report, and the in-process API. Fixtures are
written as bytes under tmp_path, never under plugins/planwise/."""
import dataclasses
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import backlog_migration as bm
import migrate_backlog_index as mig
import migrate_backlog_support as sup
import migration_answers
from config_gen import InitConfig

NO_GIT = "--allow-untracked-tree"
HEADER = "| ID | Feature | Priority | Status | Created | Blocks | Files |\n|---|---|---|---|---|---|---|\n"
HEADER_NO_CREATED = "| ID | Feature | Priority | Status | Blocks | Files |\n|---|---|---|---|---|---|\n"
FOOTER = "*Last Updated: 2024-01-01 — did something. Prior entry: 2023-12-01 — did something else.*\n"
NAMES = {i: f"ITM-{i}-SMP-{n}.md" for i, n in (("001", "First"), ("002", "Second"), ("003", "Third"),
                                               ("004", "Fourth"))}
TITLES = {"001": "First sample item", "002": "Second sample item", "003": "Third sample item",
          "004": "Fourth sample item"}
DEPS_TABLE = "## Dependencies\n\n| ID | Blocks |\n|---|---|\n| 001 | 002 |\n\n"
SOFT_HEADING = "**Soft dependencies**"
BULLET = "- 002 relates to 001 (shared parser)"
SOFT = f"{SOFT_HEADING}\n\n{BULLET}\n\n"
DEPS_HEADING = "## Dependency Notes (migrated from the backlog index)"
HEADER_ONLY = "[← 00-Index-Backlog.md](00-Index-Backlog.md)\n"
ALL_FLAGS = ("--backfill-frontmatter", "--write-edges", "--extract-dependency-notes", "--reconcile", "index-wins")
MIGRATED_INDEX = ("Generated: 2024-01-01\n\n| ID | Title | Priority | Status | Domain | Created | Blocks | Score | File |\n"
                  "|---|---|---|---|---|---|---|---|---|\n")
UNRECOGNIZED_INDEX = ("## Backlog Items\n\n| ID | Feature | Owner | Files |\n|---|---|---|---|\n"
                      "| 001 | First sample item | nobody | [001](ITM-001-SMP-First.md) |\n\n" + FOOTER)


def fm(item_id, status="NOT_STARTED", blocks="[]", drop=()):
    keys = {"id": item_id, "title": f'"{TITLES[item_id]}"', "priority": "High", "status": status,
            "abbrev": "SMP", "created": "2024-01-01", "blocks": blocks}
    return "\n".join(["---"] + [f"{k}: {v}" for k, v in keys.items() if k not in drop] + ["---", ""]) + "\n"


def item(item_id, head=None, body="Body text."):
    return (fm(item_id) if head is None else head) + f"# {TITLES[item_id]}\n\n{body}\n"


def row(item_id, status="NOT_STARTED", blocks="", created="2024-01-01"):
    cells = [item_id, TITLES[item_id], "High", status] + ([created] if created is not None else [])
    return "| " + " | ".join(cells + [blocks, f"[{item_id}]({NAMES[item_id]})"]) + " |\n"


def index(*rows, deps="", header=HEADER):
    return f"# Backlog Index\n\n## Backlog Items\n\n{header}{''.join(rows)}\n{deps}{FOOTER}"


def project(tmp_path, index_text, items, changelog=None):
    planwise = tmp_path / "proj" / "planwise"
    backlog = planwise / "Backlog"
    (backlog / "Archive").mkdir(parents=True)
    for item_id, text in items.items():
        (backlog / NAMES[item_id]).write_bytes(text.encode("utf-8"))
    (planwise / "config.yaml").write_bytes(b'project:\n  name: "test-project"\n  backlog_dir: "Backlog"\n'
                                           b'  index_files:\n    backlog: "00-Index-Backlog.md"\n')
    index_path = backlog / "00-Index-Backlog.md"
    index_path.write_bytes(index_text.encode("utf-8"))
    if changelog is not None:
        (backlog / "00-Changelog-Backlog.md").write_bytes(changelog.encode("utf-8"))
    return planwise / "config.yaml", index_path


def snapshot(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def run(monkeypatch, capsys, config_path, *args):
    monkeypatch.setattr(sys, "argv", ["migrate_backlog_index.py", "--config", str(config_path), NO_GIT, *args])
    code = mig.main()
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def ledger(index_path):
    return json.loads(mig.artifact_paths(index_path)[1].read_bytes().decode("utf-8"))


def item_bytes(index_path, item_id):
    return (index_path.parent / NAMES[item_id]).read_bytes()


def write_then_clean(tmp_path, monkeypatch, capsys, config_path, *flags):
    """First --write succeeds; a second --write prints CLEAN and leaves the tree byte-identical."""
    code, out, err = run(monkeypatch, capsys, config_path, *flags, "--write")
    assert code == 0, err + out
    after = snapshot(tmp_path)
    code, out, err = run(monkeypatch, capsys, config_path, *flags, "--write")
    assert code == 0 and "CLEAN" in out, err + out
    assert snapshot(tmp_path) == after


def refused(tmp_path, monkeypatch, capsys, config_path, fragments, *flags):
    before = snapshot(tmp_path)
    code, out, err = run(monkeypatch, capsys, config_path, "--force", "--write", *flags)
    assert code == 2, err + out
    assert all(fragment in err for fragment in fragments), err
    assert snapshot(tmp_path) == before


RICH_INDEX = index(row("001", blocks="002"), row("002"), row("003"), deps=DEPS_TABLE + SOFT)
RICH_ITEMS = {"001": item("001"), "002": item("002"), "003": item("003", head="")}


@pytest.mark.parametrize("head,fragments", [
    ("", ["generator", "no well-formed frontmatter", "add --backfill-frontmatter"]),
    (fm("003", drop=("created", "blocks")), ["created", "generator", "add --backfill-frontmatter"]),
], ids=["no-block", "partial-block"])
def test_backfill_off_refuses_and_names_the_flag(tmp_path, monkeypatch, capsys, head, fragments):
    config_path, _ = project(tmp_path, index(row("001"), row("003")), {"001": item("001"), "003": item("003", head)})
    refused(tmp_path, monkeypatch, capsys, config_path, fragments)


def test_backfill_writes_a_block_and_only_the_missing_keys(tmp_path, monkeypatch, capsys):
    partial = item("004", head=fm("004", drop=("created", "blocks")))
    items = {"001": item("001"), "003": item("003", head=""), "004": partial}
    config_path, index_path = project(tmp_path, index(row("001"), row("003"), row("004")), items)
    write_then_clean(tmp_path, monkeypatch, capsys, config_path, "--backfill-frontmatter")
    assert item_bytes(index_path, "003") == (fm("003") + "# Third sample item\n\nBody text.\n").encode()
    assert item_bytes(index_path, "004") == partial.replace(
        "abbrev: SMP\n---", "abbrev: SMP\ncreated: 2024-01-01\nblocks: []\n---").encode()
    entries = {Path(e["path"]).name: e for e in ledger(index_path)["backfill"]}
    assert entries[NAMES["003"]] == {"path": entries[NAMES["003"]]["path"], "created_source": "index",
                                     "keys_added": ["id", "title", "priority", "status", "abbrev", "created", "blocks"]}
    assert entries[NAMES["004"]]["keys_added"] == ["created", "blocks"]
    assert ledger(index_path)["verification"] == {"verified": True, "misses": []}


def test_backfill_created_falls_back_to_mtime_without_a_created_column_or_git(tmp_path, monkeypatch, capsys):
    rows = row("001", created=None) + row("003", created=None)
    items = {"001": item("001"), "003": item("003", head="")}
    config_path, index_path = project(tmp_path, index(rows, header=HEADER_NO_CREATED), items)
    os.utime(index_path.parent / NAMES["003"], (1_700_000_000, 1_700_000_000))
    code, out, err = run(monkeypatch, capsys, config_path, "--backfill-frontmatter", "--write")
    assert code == 0, err + out
    expected = datetime.fromtimestamp(1_700_000_000, tz=timezone.utc).astimezone().date().isoformat()
    assert f"created: {expected}\n".encode() in item_bytes(index_path, "003")
    assert ledger(index_path)["backfill"][0]["created_source"] == "mtime"


def test_backfill_refuses_a_frontmatterless_file_no_row_names(tmp_path, monkeypatch, capsys):
    config_path, _ = project(tmp_path, index(row("001")), {"001": item("001"), "003": item("003", head="")})
    refused(tmp_path, monkeypatch, capsys, config_path, [NAMES["003"], "no index row names it"],
            "--backfill-frontmatter")


def test_write_edges_off_refuses_and_names_the_flag(tmp_path, monkeypatch, capsys):
    items = {"001": item("001"), "002": item("002")}
    config_path, _ = project(tmp_path, index(row("001", blocks="002"), row("002"), deps=DEPS_TABLE), items)
    refused(tmp_path, monkeypatch, capsys, config_path, ["001 blocks 002", "add --write-edges"])


def test_write_edges_unions_the_edge_into_blocks(tmp_path, monkeypatch, capsys):
    items = {"001": item("001"), "002": item("002")}
    config_path, index_path = project(tmp_path, index(row("001", blocks="002"), row("002"), deps=DEPS_TABLE), items)
    write_then_clean(tmp_path, monkeypatch, capsys, config_path, "--write-edges")
    assert item_bytes(index_path, "001") == items["001"].replace("blocks: []", "blocks: [002]").encode()
    assert item_bytes(index_path, "002") == items["002"].encode()
    assert ledger(index_path)["edges"] == [{"src": "001", "dst": "002"}]
    assert b"| 001 | 002 |" in index_path.read_bytes()


def test_extract_dependency_notes_off_relocates_the_bullet_verbatim(tmp_path, monkeypatch, capsys):
    items = {"001": item("001", head=fm("001", blocks="[002]")), "002": item("002")}
    text = index(row("001", blocks="002"), row("002"), deps=DEPS_TABLE + SOFT)
    config_path, index_path = project(tmp_path, text, items)
    code, out, err = run(monkeypatch, capsys, config_path, "--force", "--write")
    assert code == 0, err + out
    first = mig.artifact_paths(index_path)[0].read_bytes().decode("utf-8").split("## Entry 2")[0]
    assert "Relocated index text (migrated " in first
    assert f"(text under a section): {SOFT_HEADING}\n" in first and f"(text under a section): {BULLET}\n" in first
    assert item_bytes(index_path, "002") == items["002"].encode()
    assert ledger(index_path)["changelog"]["unaccounted"] == 0


def test_extract_dependency_notes_moves_the_bullet_to_its_owner(tmp_path, monkeypatch, capsys):
    items = {"001": item("001", head=fm("001", blocks="[002]")), "002": item("002")}
    text = index(row("001", blocks="002"), row("002"), deps=DEPS_TABLE + SOFT)
    config_path, index_path = project(tmp_path, text, items)
    write_then_clean(tmp_path, monkeypatch, capsys, config_path, "--extract-dependency-notes")
    assert item_bytes(index_path, "002") == (items["002"] + f"\n{DEPS_HEADING}\n\n{BULLET}\n").encode()
    migrated = index_path.read_bytes().decode("utf-8")
    assert BULLET not in migrated and SOFT_HEADING not in migrated and "| 001 | 002 |" in migrated
    log = ledger(index_path)
    assert [(Path(n["path"]).name, n["bullets"], n["bytes"]) for n in log["dependency_notes"]] == [
        (NAMES["002"], 1, len(BULLET.encode()))]
    assert log["dependency_headings_dropped"] == [SOFT_HEADING]


def test_reconcile_default_refusal_names_both_modes(tmp_path, monkeypatch, capsys):
    config_path, _ = project(tmp_path, index(row("001", status="IN_PROGRESS")), {"001": item("001")})
    refused(tmp_path, monkeypatch, capsys, config_path,
            ["disagree", "Status", "IN_PROGRESS", "--reconcile index-wins", "--reconcile frontmatter-wins"])


@pytest.mark.parametrize("mode,expected_status", [("index-wins", "IN_PROGRESS"), ("frontmatter-wins", "NOT_STARTED")])
def test_reconcile_mode_settles_the_disagreement(tmp_path, monkeypatch, capsys, mode, expected_status):
    original = item("001")
    config_path, index_path = project(tmp_path, index(row("001", status="IN_PROGRESS")), {"001": original})
    write_then_clean(tmp_path, monkeypatch, capsys, config_path, "--reconcile", mode)
    expected = original.replace("status: NOT_STARTED", f"status: {expected_status}")
    assert item_bytes(index_path, "001") == expected.encode()
    assert ledger(index_path)["reconcile"] == {"mode": mode, "cells": [
        {"id": "001", "key": "status", "frontmatter": "NOT_STARTED", "index": "IN_PROGRESS"}]}


@pytest.mark.parametrize("header", [HEADER_ONLY, HEADER_ONLY.replace("\n", "\r\n")], ids=["lf", "crlf"])
def test_header_only_changelog_is_filled(tmp_path, monkeypatch, capsys, header):
    config_path, index_path = project(tmp_path, index(row("001")), {"001": item("001")}, changelog=header)
    write_then_clean(tmp_path, monkeypatch, capsys, config_path)
    changelog = mig.artifact_paths(index_path)[0].read_bytes().decode("utf-8")
    assert "did something" in changelog and "did something else" in changelog
    assert ledger(index_path)["changelog"]["header_only"] is True


def test_foreign_changelog_is_still_refused_under_every_flag(tmp_path, monkeypatch, capsys):
    config_path, _ = project(tmp_path, index(row("001")), {"001": item("001")}, changelog="other\n")
    refused(tmp_path, monkeypatch, capsys, config_path, ["already exists"], *ALL_FLAGS)


REFUSALS_UNDER_ALL_FLAGS = [
    ("reciprocal", index(row("001", blocks="002"), row("002", blocks="001"), deps=DEPS_TABLE),
     {"001": item("001"), "002": item("002", head=fm("002", blocks="[001]"))}, ["reciprocal", "001<->002"]),
    ("no-row-no-block", index(row("001")), {"001": item("001"), "003": item("003", head="")}, ["no index row names it"]),
    ("unclosed-block", index(row("001"), row("003")), {"001": item("001"), "003": item("003", head="---\nid: 003\n")},
     ["does not close"]),
    ("blocks-prose", index(row("001", blocks="002 (soft)"), row("002")),
     {"001": item("001", head=fm("001", blocks="[002]")), "002": item("002")}, ["other than ids", "cannot settle"]),
]


@pytest.mark.parametrize("text,items,fragments", [pytest.param(*r[1:], id=r[0]) for r in REFUSALS_UNDER_ALL_FLAGS])
def test_every_refusal_under_all_flags_writes_nothing(tmp_path, monkeypatch, capsys, text, items, fragments):
    config_path, _ = project(tmp_path, text, items)
    refused(tmp_path, monkeypatch, capsys, config_path, fragments, *ALL_FLAGS)


@pytest.mark.parametrize("text,shape", [(RICH_INDEX, "legacy"), (MIGRATED_INDEX, "generated"),
                                        (UNRECOGNIZED_INDEX, "unrecognized")])
def test_report_is_read_only_json_on_every_shape(tmp_path, monkeypatch, capsys, text, shape):
    config_path, _ = project(tmp_path, text, RICH_ITEMS, changelog=HEADER_ONLY)
    before = snapshot(tmp_path)
    code, out, err = run(monkeypatch, capsys, config_path, "--report")
    assert code == 0, err + out
    report = json.loads(out)
    assert report["shape"] == shape and report["changelog"] == "header-only"
    assert report["items"]["without_frontmatter"] == 1
    assert report["ready_with_all_repairs"] is (shape != "unrecognized")
    assert snapshot(tmp_path) == before


def test_report_counts_the_legacy_gaps(tmp_path, monkeypatch, capsys):
    config_path, _ = project(tmp_path, RICH_INDEX, RICH_ITEMS)
    code, out, err = run(monkeypatch, capsys, config_path, "--report", "--json")
    assert code == 0, err + out
    report = json.loads(out)
    assert report["changelog"] == "missing" and report["row_mismatches"] == 1 and report["would_refuse"] == []
    assert report["items"] == {"total": 3, "without_frontmatter": 1, "partial_frontmatter": 0,
                               "unreferenced_without_frontmatter": 0}
    assert report["dependencies"] == {"bare_edges": 1, "edges_missing_from_blocks": 1, "soft_dependency_bullets": 1,
                                      "unrecognised_lines": 0}


def test_report_is_ready_for_an_unknown_owner_bullet_and_it_relocates(tmp_path, monkeypatch, capsys):
    bullet = "- 009 relates to 001"
    text = index(row("001"), deps=f"## Dependencies\n\n| ID | Blocks |\n|---|---|\n\n{bullet}\n\n")
    config_path, index_path = project(tmp_path, text, {"001": item("001")})
    before = snapshot(tmp_path)
    code, out, _err = run(monkeypatch, capsys, config_path, "--report")
    report = json.loads(out)
    assert code == 0 and report["ready_with_all_repairs"] is True and report["would_refuse"] == []
    assert snapshot(tmp_path) == before
    code, out, err = run(monkeypatch, capsys, config_path, "--force", "--write", *ALL_FLAGS)
    assert code == 0, err + out
    first = mig.artifact_paths(index_path)[0].read_bytes().decode("utf-8").split("## Entry 2")[0]
    assert f"(unknown-owner bullet): {bullet}\n" in first
    assert ledger(index_path)["changelog"]["unaccounted"] == 0


def test_report_and_write_are_mutually_exclusive(tmp_path, monkeypatch, capsys):
    config_path, _ = project(tmp_path, RICH_INDEX, RICH_ITEMS)
    before = snapshot(tmp_path)
    code, _out, err = run(monkeypatch, capsys, config_path, "--report", "--write")
    assert code == 2 and "mutually exclusive" in err
    assert snapshot(tmp_path) == before


def test_in_process_plan_targets_then_execute(tmp_path, monkeypatch, capsys):
    config_path, index_path = project(tmp_path, RICH_INDEX, RICH_ITEMS, changelog=HEADER_ONLY)
    monkeypatch.setattr(sys, "argv", ["migrate_backlog_index.py", "--config", str(config_path)])
    config = mig.load_config(Path(mig.__file__))
    text = mig.read_text(index_path)
    _shape, detail = sup.classify_shape(text)
    plan = mig.plan_migration(config, index_path, text, detail, mig.RepairOptions.all_on())
    changelog, ledger_path, _older = mig.artifact_paths(index_path)
    assert {p.name for p in mig.plan_targets(plan)} == {index_path.name, changelog.name, *NAMES.values()} - {
        NAMES["004"]}
    assert ledger_path.name not in {p.name for p in mig.plan_targets(plan)}
    assert mig.execute(plan, mig.artifact_paths(index_path), index_path, False) == 0
    log = ledger(index_path)
    assert log["verification"] == {"verified": True, "misses": []}
    assert (len(log["backfill"]), len(log["edges"]), len(log["dependency_notes"])) == (1, 1, 1)
    capsys.readouterr()


HEADER_ABBREV = "| ID | Feature | Priority | Status | Abbrev | Files |\n|---|---|---|---|---|---|\n"


def test_file_name_wins_an_id_disagreement(tmp_path, monkeypatch, capsys):
    # The file name says 003, the index cell says 013: the file name's id goes into frontmatter and the
    # cell is recorded, not refused. The id: line is the only one missing, so it is the only one written.
    original = item("003", head=fm("003", drop=("id",)))
    cell = row("003").replace("| 003 |", "| 013 |", 1)
    config_path, index_path = project(tmp_path, index(row("001"), cell), {"001": item("001"), "003": original})
    write_then_clean(tmp_path, monkeypatch, capsys, config_path, "--backfill-frontmatter", "--reconcile", "index-wins")
    assert b"\nid: 003\n" in item_bytes(index_path, "003") and b"013" not in item_bytes(index_path, "003")
    log = ledger(index_path)
    assert log["reconcile"]["cells"] == [{"id": "003", "key": "id", "frontmatter": None, "index": "013",
                                          "winner": "file-name", "written": "003"}]
    assert log["verification"] == {"verified": True, "misses": []}


def test_file_name_wins_an_abbrev_disagreement(tmp_path, monkeypatch, capsys):
    # The file name says SMP, the cell says DOC and index-wins would normally write DOC over it.
    original = item("003", head=fm("003", drop=("abbrev",)))
    cell = f"| 003 | {TITLES['003']} | High | NOT_STARTED | DOC | [003]({NAMES['003']}) |\n"
    config_path, index_path = project(tmp_path, index(cell, header=HEADER_ABBREV), {"003": original})
    write_then_clean(tmp_path, monkeypatch, capsys, config_path, "--backfill-frontmatter", "--reconcile", "index-wins")
    assert b"\nabbrev: SMP\n" in item_bytes(index_path, "003") and b"DOC" not in item_bytes(index_path, "003")
    log = ledger(index_path)
    assert log["reconcile"]["cells"] == [{"id": "003", "key": "abbrev", "frontmatter": None, "index": "DOC",
                                          "winner": "file-name", "written": "SMP"}]
    assert log["verification"] == {"verified": True, "misses": []}


def _crash_then_resume(monkeypatch, capsys, config_path, index_path, *flags):
    """A --write that dies replacing the index, after the item files, then the same --write again."""
    real = sup._replace

    def replace(src, dst):
        if Path(dst).name == index_path.name:
            raise OSError("simulated crash")
        return real(src, dst)
    with monkeypatch.context() as m:
        m.setattr(sup, "_replace", replace)
        code, out, err = run(monkeypatch, capsys, config_path, *flags, "--write")
    assert code == 1 and "replace stopped" in err, err + out
    return run(monkeypatch, capsys, config_path, *flags, "--write")


def test_a_file_name_id_win_is_kept_on_resume(tmp_path, monkeypatch, capsys):
    cell = row("003").replace("| 003 |", "| 013 |", 1)
    config_path, index_path = project(tmp_path, index(cell), {"003": item("003", head=fm("003", drop=("id",)))})
    code, out, err = _crash_then_resume(monkeypatch, capsys, config_path, index_path,
                                        "--backfill-frontmatter", "--reconcile", "index-wins")
    assert code == 0, err + out
    assert b"\nid: 003\n" in item_bytes(index_path, "003")
    assert [(c["key"], c["index"], c["winner"], c["written"]) for c in ledger(index_path)["reconcile"]["cells"]] == [
        ("id", "013", "file-name", "003")]


def test_a_file_name_abbrev_win_is_kept_on_resume(tmp_path, monkeypatch, capsys):
    cell = f"| 003 | {TITLES['003']} | High | NOT_STARTED | DOC | [003]({NAMES['003']}) |\n"
    config_path, index_path = project(tmp_path, index(cell, header=HEADER_ABBREV),
                                      {"003": item("003", head=fm("003", drop=("abbrev",)))})
    code, out, err = _crash_then_resume(monkeypatch, capsys, config_path, index_path,
                                        "--backfill-frontmatter", "--reconcile", "index-wins")
    assert code == 0, err + out
    assert b"\nabbrev: SMP\n" in item_bytes(index_path, "003") and b"DOC" not in item_bytes(index_path, "003")
    assert [(c["key"], c["index"], c["winner"], c["written"]) for c in ledger(index_path)["reconcile"]["cells"]] == [
        ("abbrev", "DOC", "file-name", "SMP")]


def test_interrupted_journal_is_renamed_and_the_run_continues(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(mig, "_today", lambda: "2026-01-02")
    config_path, index_path = project(tmp_path, index(row("001")), {"001": item("001")})
    ledger_path = mig.artifact_paths(index_path)[1]

    def crash(*args, **kwargs):
        raise RuntimeError("simulated crash after the index was replaced, before the ledger write")
    with monkeypatch.context() as m:
        m.setattr(mig, "build_ledger", crash)
        with pytest.raises(RuntimeError, match="simulated crash"):
            run(monkeypatch, capsys, config_path, "--write")
    journal = ledger_path.read_bytes()
    assert json.loads(journal)["mode"] == sup.JOURNAL_MODE
    # A dry run names the rename and writes nothing.
    before = snapshot(tmp_path)
    code, out, err = run(monkeypatch, capsys, config_path)
    assert code == 1 and "DRY-RUN" in out + err and "-Interrupted-2026-01-02.json" in out + err
    assert snapshot(tmp_path) == before
    # --write renames the journal, keeps every byte of it, and leaves a ledger naming it.
    code, out, err = run(monkeypatch, capsys, config_path, "--write")
    assert code == 0 and "WROTE" in out, err + out
    kept = ledger_path.with_name(f"{ledger_path.stem}-Interrupted-2026-01-02.json")
    assert kept.read_bytes() == journal
    note = ledger(index_path)
    assert note["mode"] == "journal-renamed" and note["journal_renamed_to"] == str(kept)
    # The next run finds nothing left to settle.
    after = snapshot(tmp_path)
    code, out, err = run(monkeypatch, capsys, config_path, "--write")
    assert code == 0 and "CLEAN" in out, err + out
    assert snapshot(tmp_path) == after


PAIR_INDEX = index(row("001", blocks="002"), row("002", blocks="001"), deps=DEPS_TABLE)
PAIR_ITEMS = {"001": item("001"), "002": item("002", head=fm("002", blocks="[001]"))}
TWO_PAIRS_INDEX = index(row("001", blocks="002"), row("002", blocks="001"), row("003", blocks="004"),
                        row("004", blocks="003"))
TWO_PAIRS_ITEMS = {"001": item("001"), "002": item("002", head=fm("002", blocks="[001]")), "003": item("003"),
                   "004": item("004", head=fm("004", blocks="[003]"))}
BOTH_WAYS_DEPS = "## Dependencies\n\n| ID | Blocks |\n|---|---|\n| 001 | 002 |\n| 002 | 001 |\n\n"


def plan_with_drops(monkeypatch, config_path, index_path, drops):
    """Plan and execute with every repair on and `drops` as the answered edge drops; return the ledger."""
    monkeypatch.setattr(sys, "argv", ["migrate_backlog_index.py", "--config", str(config_path)])
    config = mig.load_config(Path(mig.__file__))
    text = mig.read_text(index_path)
    _shape, detail = sup.classify_shape(text)
    options = dataclasses.replace(mig.RepairOptions.all_on(), edge_drops=frozenset(drops))
    plan = mig.plan_migration(config, index_path, text, detail, options)
    assert mig.execute(plan, mig.artifact_paths(index_path), index_path, False) == 0
    log = ledger(index_path)
    assert log["verification"] == {"verified": True, "misses": []}
    return log


def report_questions(monkeypatch, capsys, config_path):
    code, out, err = run(monkeypatch, capsys, config_path, "--report", "--json")
    assert code == 0, err + out
    return json.loads(out)["questions"]


def test_edge_drop_answer_keeps_the_other_direction(tmp_path, monkeypatch, capsys):
    config_path, index_path = project(tmp_path, PAIR_INDEX, PAIR_ITEMS)
    log = plan_with_drops(monkeypatch, config_path, index_path, ["002->001"])
    assert item_bytes(index_path, "001") == PAIR_ITEMS["001"].replace("blocks: []", "blocks: [002]").encode()
    assert item_bytes(index_path, "002") == PAIR_ITEMS["002"].replace("blocks: [001]", "blocks: []").encode()
    assert log["edges"] == [{"src": "001", "dst": "002"},
                            {"src": "002", "dst": "001", "action": "dropped", "source": "answer",
                             "path": str((index_path.parent / NAMES["002"]).resolve())}]
    capsys.readouterr()


def test_edge_drop_both_clears_both_blocks(tmp_path, monkeypatch, capsys):
    config_path, index_path = project(tmp_path, PAIR_INDEX, PAIR_ITEMS)
    log = plan_with_drops(monkeypatch, config_path, index_path, ["001<->002:both"])
    assert item_bytes(index_path, "001") == PAIR_ITEMS["001"].encode()
    assert item_bytes(index_path, "002") == PAIR_ITEMS["002"].replace("blocks: [001]", "blocks: []").encode()
    assert [(e["src"], e["dst"]) for e in log["edges"]] == [("001", "002"), ("002", "001")]
    assert {e["action"] for e in log["edges"]} == {"dropped"}
    capsys.readouterr()


def test_reciprocal_without_an_answer_still_refuses_with_the_question(tmp_path, monkeypatch, capsys):
    config_path, _ = project(tmp_path, PAIR_INDEX, PAIR_ITEMS)
    refused(tmp_path, monkeypatch, capsys, config_path, ["reciprocal", "001<->002"], *ALL_FLAGS)
    questions = report_questions(monkeypatch, capsys, config_path)
    assert [q["id"] for q in questions] == ["reciprocal-edge"] and len(questions[0]["options"]) == 3


def test_reciprocal_questions_one_per_pair(tmp_path, monkeypatch, capsys):
    config_path, _ = project(tmp_path, TWO_PAIRS_INDEX, TWO_PAIRS_ITEMS)
    questions = report_questions(monkeypatch, capsys, config_path)
    assert [q["id"] for q in questions] == ["reciprocal-edge"] * 2
    assert [q["pairs"] for q in questions] == [[["001", "002"]], [["003", "004"]]]
    for q in questions:
        a, b = q["pairs"][0]
        assert (a in q["prompt"], b in q["prompt"]) == (True, True)
        assert [o["answer"] for o in q["options"]] == [{"edge_drops": [f"{b}->{a}"]}, {"edge_drops": [f"{a}->{b}"]},
                                                       {"edge_drops": [f"{a}<->{b}:both"]}]


def test_each_option_payload_is_accepted_through_answers(tmp_path, monkeypatch, capsys):
    # The pair reaches the migrator through the '## Dependencies' table, so the drop must also remove the union edge.
    expected = [("[002]", "[]"), ("[]", "[001]"), ("[]", "[]")]  # per option: a blocks b, b blocks a, drop both
    for option, (blocks_001, blocks_002) in enumerate(expected):
        root = tmp_path / f"option-{option}"
        items = {"001": item("001"), "002": item("002")}
        config_path, index_path = project(root, index(row("001"), row("002"), deps=BOTH_WAYS_DEPS), items)
        answer = report_questions(monkeypatch, capsys, config_path)[0]["options"][option]["answer"]
        cfg = InitConfig(project_name="test-project", project_root=root / "proj", plugin_root=SCRIPTS.parent)
        report = bm.migrate_backlog_if_legacy(cfg, "1.0", "1.1", answers=answer)
        assert report.state == "migrated", (option, report.detail)
        assert f"blocks: {blocks_001}" in item_bytes(index_path, "001").decode(), option
        assert f"blocks: {blocks_002}" in item_bytes(index_path, "002").decode(), option
    capsys.readouterr()


# --- answered edge drops: the removal touches only the named entry, and only a reciprocal direction ---

def plan_for(monkeypatch, config_path, index_path, drops, reconcile="index-wins"):
    """Plan (without executing) with every repair on and `drops` as the answered edge drops."""
    monkeypatch.setattr(sys, "argv", ["migrate_backlog_index.py", "--config", str(config_path)])
    config = mig.load_config(Path(mig.__file__))
    text = mig.read_text(index_path)
    _shape, detail = sup.classify_shape(text)
    options = dataclasses.replace(mig.RepairOptions.all_on(reconcile), edge_drops=frozenset(drops))
    return mig.plan_migration(config, index_path, text, detail, options)


def run_plan(monkeypatch, config_path, index_path, drops, reconcile="index-wins"):
    """Plan and execute; return (plan, ledger) after checking the write verified from disk."""
    plan = plan_for(monkeypatch, config_path, index_path, drops, reconcile)
    assert mig.execute(plan, mig.artifact_paths(index_path), index_path, False) == 0
    log = ledger(index_path)
    assert log["verification"] == {"verified": True, "misses": []}
    return plan, log


def three_items(tmp_path, head_002, row_002="001, 004"):
    items = {"001": item("001", head=fm("001", blocks="[002]")), "002": item("002", head=head_002), "004": item("004")}
    return project(tmp_path, index(row("001", blocks="002"), row("002", blocks=row_002), row("004")), items)


def dropped_pairs(log):
    return [(e["src"], e["dst"]) for e in log["edges"] if e.get("action") == "dropped"]


def test_drop_ignores_digits_in_an_inline_comment(tmp_path, monkeypatch, capsys):
    head = fm("002", blocks="[001, 004] # split from 007-02")
    config_path, index_path = three_items(tmp_path, head)
    _plan, log = run_plan(monkeypatch, config_path, index_path, ["002->001"])
    assert item_bytes(index_path, "002") == item("002", head=fm("002", blocks="[004] # split from 007-02")).encode()
    assert dropped_pairs(log) == [("002", "001")]
    capsys.readouterr()


@pytest.mark.parametrize("before,after,row_cell,mode", [
    ("\n  - '001'\n  - \"004\" # keep this note", "\n  - \"004\" # keep this note", "001, 004", "index-wins"),
    ("[ '001' ,  \"004\" ,004 ]  # note", "[ \"004\" ,004 ]  # note", "001, 004", "frontmatter-wins"),
    ("[004, 001, 004]", "[004, 004]", "001, 004", "frontmatter-wins"),
    ("[1, 004]", "[004]", "001, 004", "index-wins"),
    ("\n  - 001", "[]", "001", "index-wins"),
    ("\n  - 004\n  # was 003\n  - 001", "\n  - 004\n  # was 003", "001, 004", "index-wins"),
    ("\n  # first\n  - 001\n  - 004", "\n  # first\n  - 004", "001, 004", "index-wins"),
    ("\n  - 004\n\n  - 001", "\n  - 004\n", "001, 004", "index-wins"),
    ("[004,\n  001]", "[004]", "001, 004", "index-wins"),
    ("[001,\n  004]", "[004]", "001, 004", "index-wins"),
    ("[004, # keep\n  001]", "[004 # keep\n  ]", "001, 004", "index-wins"),
    ("[004, 001,]", "[004, ]", "001, 004", "index-wins"),
    ("\t[001,\t004]", "\t[004]", "001, 004", "index-wins"),
], ids=["block-form", "quoted-padded-flow", "duplicate-kept", "unpadded-id", "block-emptied",
        "comment-line-in-block", "comment-before-entry", "blank-line-in-block", "multiline-flow-last",
        "multiline-flow-first", "multiline-flow-comment", "trailing-comma", "tab-flow"])
def test_drop_removes_only_the_named_entry(tmp_path, monkeypatch, capsys, before, after, row_cell, mode):
    config_path, index_path = three_items(tmp_path, fm("002", blocks=before), row_cell)
    run_plan(monkeypatch, config_path, index_path, ["002->001"], mode)
    assert item_bytes(index_path, "002") == item("002", head=fm("002", blocks=after)).encode()
    capsys.readouterr()


def test_drop_of_a_direction_whose_reverse_is_gone_is_not_applied(tmp_path, monkeypatch, capsys):
    # The user answered, then removed 001 -> 002 by hand: 002 -> 001 is now a valid one-way edge.
    items = {"001": item("001"), "002": item("002", head=fm("002", blocks="[001]"))}
    config_path, index_path = project(tmp_path, index(row("001"), row("002", blocks="001")), items)
    _plan, log = run_plan(monkeypatch, config_path, index_path, ["002->001"])
    assert item_bytes(index_path, "002") == items["002"].encode()
    assert dropped_pairs(log) == []
    (entry,) = [e for e in log["edges"] if e.get("action") == "answer-not-applied"]
    assert (entry["src"], entry["dst"], entry["source"]) == ("002", "001", "answer") and entry["reason"]
    capsys.readouterr()


def test_drop_reaches_an_unindexed_item_file(tmp_path, monkeypatch, capsys):
    items = {"001": item("001", head=fm("001", blocks="[002]"))}
    config_path, index_path = project(tmp_path, index(row("001", blocks="002")), items)
    archived = index_path.parent / "Archive" / NAMES["002"]
    archived.write_bytes(item("002", head=fm("002", blocks="[001]")).encode())
    _plan, log = run_plan(monkeypatch, config_path, index_path, ["002->001"])
    assert archived.read_bytes() == item("002").encode()
    assert dropped_pairs(log) == [("002", "001")]
    capsys.readouterr()


def test_an_answer_that_matches_no_edge_is_reported(tmp_path, monkeypatch, capsys):
    config_path, index_path = project(tmp_path, PAIR_INDEX, PAIR_ITEMS)
    plan, log = run_plan(monkeypatch, config_path, index_path, ["0001->0002", "002->001"])
    (entry,) = [e for e in log["edges"] if e.get("action") == "answer-not-applied"]
    assert (entry["src"], entry["dst"]) == ("0001", "0002") and entry["reason"]
    assert dropped_pairs(log) == [("002", "001")]
    assert "0001->0002" in mig.format_report(plan)
    capsys.readouterr()


def test_a_refusal_names_the_answers_that_matched_nothing(tmp_path, monkeypatch, capsys):
    config_path, index_path = project(tmp_path, PAIR_INDEX, PAIR_ITEMS)
    before = snapshot(tmp_path)
    with pytest.raises(mig.Refusal) as exc:
        plan_for(monkeypatch, config_path, index_path, ["0001->0002"])
    assert "reciprocal" in exc.value.reason and "0001->0002" in exc.value.reason
    assert snapshot(tmp_path) == before
    capsys.readouterr()


def interrupt_before_index(monkeypatch):
    """Make the first replace stop after the journal and item files, before the changelog and index."""
    real = sup.replace_all

    def partial(staged):
        if len(staged) > 2 and staged[0][1].name.endswith("Migration-Ledger.json"):
            real(staged[:-2])
            sup.discard(staged[-2:])
            raise sup.ReplaceError(staged[-2][1], [], OSError("simulated crash"))
        return real(staged)
    monkeypatch.setattr(sup, "replace_all", partial)


@pytest.mark.parametrize("resume_drops", [[], ["002->001"]], ids=["without-answers", "with-answers"])
def test_a_drop_survives_a_crash_after_the_item_files(tmp_path, monkeypatch, capsys, resume_drops):
    config_path, index_path = project(tmp_path, PAIR_INDEX, PAIR_ITEMS)
    plan = plan_for(monkeypatch, config_path, index_path, ["002->001"])
    with monkeypatch.context() as m:
        interrupt_before_index(m)
        assert mig.execute(plan, mig.artifact_paths(index_path), index_path, False) == 1
    cleared = PAIR_ITEMS["002"].replace("blocks: [001]", "blocks: []").encode()
    assert item_bytes(index_path, "002") == cleared
    assert json.loads(mig.artifact_paths(index_path)[1].read_bytes())["mode"] == sup.JOURNAL_MODE
    resumed, log = run_plan(monkeypatch, config_path, index_path, resume_drops)
    assert item_bytes(index_path, "002") == cleared
    assert dropped_pairs(log) == [("002", "001")]
    (dropped,) = [e for e in resumed["edges"] if e.get("action") == "dropped"]
    assert dropped["path"] == (index_path.parent / NAMES["002"]).resolve()
    (entry,) = [e for e in log["edges"] if e.get("action") == "dropped"]
    assert entry["source"] == ("answer" if resume_drops else "journal")
    assert entry["path"] == str(dropped["path"])
    capsys.readouterr()


def test_a_malformed_drop_entry_refuses_before_any_write(tmp_path, monkeypatch, capsys):
    config_path, index_path = project(tmp_path, PAIR_INDEX, PAIR_ITEMS)
    before = snapshot(tmp_path)
    for entry in ("002 -> 001", "002->", "00a->001", "002<->001", "001->001", "002->2"):
        with pytest.raises(mig.Refusal) as exc:
            plan_for(monkeypatch, config_path, index_path, [entry])
        assert exc.value.reason == migration_answers.bad_edge_drop_reason(entry)
        assert exc.value.fix == migration_answers.EDGE_DROP_FIX
        assert snapshot(tmp_path) == before
    cfg = InitConfig(project_name="test-project", project_root=tmp_path / "proj", plugin_root=SCRIPTS.parent)
    report = bm.migrate_backlog_if_legacy(cfg, "1.0", "1.1", answers={"edge_drops": ["002 -> 001"]})
    assert report.state == "refused" and "'002 -> 001'" in report.detail
    assert snapshot(tmp_path) == before
    capsys.readouterr()


def migrated_banner(tmp_path, index_text, items, answers):
    _config_path, index_path = project(tmp_path, index_text, items)
    cfg = InitConfig(project_name="test-project", project_root=tmp_path / "proj", plugin_root=SCRIPTS.parent)
    report = bm.migrate_backlog_if_legacy(cfg, "1.0", "1.1", answers=answers)
    assert report.state == "migrated", report.detail
    return report, "\n".join(bm._banner_lines(report)), index_path


def test_banner_names_the_dropped_directions(tmp_path, capsys):
    report, banner, index_path = migrated_banner(tmp_path, PAIR_INDEX, PAIR_ITEMS, {"edge_drops": ["002->001"]})
    assert "blocks: edges dropped by answer: 1 (002->001)" in banner
    assert "answers not applied" not in banner
    assert report.counts["edges"] == 1
    assert [(e["src"], e["dst"]) for e in ledger(index_path)["edges"]] == [("001", "002"), ("002", "001")]
    capsys.readouterr()


def test_banner_names_the_answers_not_applied(tmp_path, capsys):
    items = {"001": item("001"), "002": item("002", head=fm("002", blocks="[001]"))}
    _report, banner, _ = migrated_banner(tmp_path, index(row("001"), row("002", blocks="001")), items,
                                         {"edge_drops": ["002->001"]})
    assert "edges dropped by answer" not in banner
    assert "answers not applied:" in banner and "002->001" in banner
    capsys.readouterr()


# --- one edge model for the refusal and the applicability test, and a journal that cannot delete a valid edge ---

def write_journal(index_path, drops):
    mig.artifact_paths(index_path)[1].write_text(
        json.dumps({"mode": sup.JOURNAL_MODE, "targets": [], "parked_ambiguous": [], "drops": drops}), encoding="utf-8")


def no_cell(root):
    items = {"001": item("001", head=fm("001", blocks="[002]")), "002": item("002", head=fm("002", blocks="[001]"))}
    return project(root, index(row("001", blocks="002"), row("002")), items)


def files_only(root):
    items = {"001": item("001", head=fm("001", blocks="[002]")), "002": item("002", head=fm("002", blocks="[001]"))}
    return project(root, index(row("001"), row("002")), items)


def cells_only(root):
    return project(root, index(row("001", blocks="002"), row("002", blocks="001")),
                   {"001": item("001"), "002": item("002")})


def deps_only(root):
    return project(root, index(row("001"), row("002"), deps=BOTH_WAYS_DEPS), {"001": item("001"), "002": item("002")})


def two_pairs(root):
    return project(root, TWO_PAIRS_INDEX, TWO_PAIRS_ITEMS)


def a_pair(root):
    return project(root, PAIR_INDEX, PAIR_ITEMS)


def test_a_pair_that_reconcile_resolves_is_not_refused(tmp_path, monkeypatch, capsys):
    # Both files block each other, but 002's Blocks cell is empty and index-wins writes the cell.
    config_path, index_path = no_cell(tmp_path)
    _plan, log = run_plan(monkeypatch, config_path, index_path, [])
    assert b"blocks: []" in item_bytes(index_path, "002") and b"blocks: [002]" in item_bytes(index_path, "001")
    assert dropped_pairs(log) == []
    capsys.readouterr()


# name -> (builder, reconcile mode): every source a reciprocal pair reaches the generator from
REFUSING_SCENARIOS = {"cells-and-deps-index-wins": (a_pair, "index-wins"),
                      "files-frontmatter-wins": (files_only, "frontmatter-wins"),
                      "cells-only-index-wins": (cells_only, "index-wins"),
                      "deps-index-wins": (deps_only, "index-wins"),
                      "deps-frontmatter-wins": (deps_only, "frontmatter-wins"),
                      "two-pairs-index-wins": (two_pairs, "index-wins")}


@pytest.mark.parametrize("name", REFUSING_SCENARIOS)
def test_every_offered_option_settles_its_pair(tmp_path, monkeypatch, capsys, name):
    """Invariant: enumerate the refusal the migrator raises, then feed every option of every question back
    as the answer. Each run must migrate, verify from disk, and skip nothing."""
    build, mode = REFUSING_SCENARIOS[name]
    config_path, index_path = build(tmp_path / "probe")
    with pytest.raises(mig.Refusal) as exc:
        plan_for(monkeypatch, config_path, index_path, [], mode)
    questions = mig.refusal_questions(exc.value)
    assert questions, name
    for q_at, question in enumerate(questions):
        for o_at, option in enumerate(question["options"]):
            answers = [entry for at, other in enumerate(questions)
                       for entry in (option if at == q_at else other["options"][0])["answer"]["edge_drops"]]
            config_path, index_path = build(tmp_path / f"run-{q_at}-{o_at}")
            _plan, log = run_plan(monkeypatch, config_path, index_path, answers, mode)
            skipped = [e for e in log["edges"] if e.get("action") == "answer-not-applied"]
            assert skipped == [], (name, q_at, o_at, skipped)
    capsys.readouterr()


def test_a_journaled_drop_is_not_replayed_on_a_one_way_edge(tmp_path, monkeypatch, capsys):
    # After the crash the user kept 002 -> 001 and removed 001 -> 002 by hand.
    items = {"001": item("001"), "002": item("002", head=fm("002", blocks="[001]"))}
    config_path, index_path = project(tmp_path, index(row("001"), row("002", blocks="001")), items)
    write_journal(index_path, [{"src": "002", "dst": "001", "path": "x"}])
    _plan, log = run_plan(monkeypatch, config_path, index_path, [])
    assert item_bytes(index_path, "002") == items["002"].encode()
    assert dropped_pairs(log) == []
    (entry,) = [e for e in log["edges"] if e.get("action") == "answer-not-applied"]
    assert (entry["src"], entry["dst"], entry["source"]) == ("002", "001", "journal") and "one-way" in entry["reason"]
    capsys.readouterr()


def test_an_answer_that_conflicts_with_the_journal_drops_one_direction(tmp_path, monkeypatch, capsys):
    config_path, index_path = a_pair(tmp_path)
    write_journal(index_path, [{"src": "002", "dst": "001", "path": "x"}])
    _plan, log = run_plan(monkeypatch, config_path, index_path, ["001->002"])
    assert dropped_pairs(log) == [("001", "002")]
    assert item_bytes(index_path, "002") == PAIR_ITEMS["002"].encode()
    (entry,) = [e for e in log["edges"] if e.get("action") == "answer-not-applied"]
    assert (entry["src"], entry["dst"], entry["source"]) == ("002", "001", "journal") and "answer" in entry["reason"]
    capsys.readouterr()


@pytest.mark.parametrize("transform", [lambda s: s.replace("\n", "\r\n"), lambda s: "﻿" + s], ids=["crlf", "bom"])
def test_drop_keeps_line_endings_and_bom(tmp_path, monkeypatch, capsys, transform):
    config_path, index_path = three_items(tmp_path, fm("002", blocks="\n  - 004\n  - 001"))
    target = index_path.parent / NAMES["002"]
    target.write_bytes(transform(target.read_bytes().decode("utf-8")).encode("utf-8"))
    run_plan(monkeypatch, config_path, index_path, ["002->001"])
    assert target.read_bytes() == transform(item("002", head=fm("002", blocks="\n  - 004"))).encode("utf-8")
    capsys.readouterr()


def test_a_journaled_drop_is_bannered_as_an_interrupted_run(tmp_path, monkeypatch, capsys):
    config_path, index_path = a_pair(tmp_path)
    plan = plan_for(monkeypatch, config_path, index_path, ["002->001"])
    with monkeypatch.context() as m:
        interrupt_before_index(m)
        assert mig.execute(plan, mig.artifact_paths(index_path), index_path, False) == 1
    cfg = InitConfig(project_name="test-project", project_root=tmp_path / "proj", plugin_root=SCRIPTS.parent)
    report = bm.migrate_backlog_if_legacy(cfg, "1.0", "1.1")
    assert report.state == "migrated", report.detail
    banner = "\n".join(bm._banner_lines(report))
    assert "dropped by an interrupted run's answer: 1 (002->001)" in banner and "dropped by answer" not in banner
    capsys.readouterr()
