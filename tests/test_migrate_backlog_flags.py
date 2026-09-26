"""Tests for the repair flags of migrate_backlog_index.py: each flag off (the
refusal keeps its old fragment and names the flag, nothing written) and on
(write, ledger section, CLEAN re-run, byte-identical tree), the header-only
changelog, the read-only --report, and the in-process API. Fixtures are
written as bytes under tmp_path, never under plugins/planwise/."""
import json
import os
import sys
from datetime import date
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import migrate_backlog_index as mig  # noqa: E402
import migrate_backlog_support as sup  # noqa: E402

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
    expected = date.fromtimestamp(1_700_000_000).isoformat()
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


def test_extract_dependency_notes_off_refuses_and_names_the_flag(tmp_path, monkeypatch, capsys):
    items = {"001": item("001", head=fm("001", blocks="[002]")), "002": item("002")}
    text = index(row("001", blocks="002"), row("002"), deps=DEPS_TABLE + SOFT)
    config_path, _ = project(tmp_path, text, items)
    refused(tmp_path, monkeypatch, capsys, config_path,
            ["text under '## Dependencies'", "Soft dependencies", "add --extract-dependency-notes"])


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
    ("unknown-owner", index(row("001"), deps="## Dependencies\n\n| ID | Blocks |\n|---|---|\n\n- 009 relates to 001\n\n"),
     {"001": item("001")}, ["soft-dependency bullet", "009"]),
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


def test_report_names_the_refusal_and_exits_0(tmp_path, monkeypatch, capsys):
    text = index(row("001"), deps="## Dependencies\n\n| ID | Blocks |\n|---|---|\n\n- 009 relates to 001\n\n")
    config_path, _ = project(tmp_path, text, {"001": item("001")})
    before = snapshot(tmp_path)
    code, out, _err = run(monkeypatch, capsys, config_path, "--report")
    report = json.loads(out)
    assert code == 0 and report["ready_with_all_repairs"] is False and "009" in report["would_refuse"][0]
    assert snapshot(tmp_path) == before


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
    shape, detail = sup.classify_shape(text)
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
