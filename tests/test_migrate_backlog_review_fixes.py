"""Regression tests for the migrator's pre-commit review fixes. Each test
fails on the code before its fix. Fixtures are written as bytes under
tmp_path, never under plugins/planwise/. Large entries are generated."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import backlog_index_schema as schema
import migrate_backlog_index as mig
import migrate_backlog_relocate as reloc
import migrate_backlog_repairs as repairs
import migrate_backlog_support as sup

NO_GIT = "--allow-untracked-tree"
BUDGET = 22000
INDEX = "00-Index-Backlog.md"
HEADER = "| ID | Feature | Priority | Status | Created | Blocks | Files |\n|---|---|---|---|---|---|---|\n"
FOOTER = "*Last Updated: 2024-01-01 — did something. Prior entry: 2023-12-01 — did something else.*\n"
MIGRATED = ("Generated: 2024-01-01\n\n| ID | Title | Priority | Status | Domain | Created | Blocks | Score | File |\n"
            "|---|---|---|---|---|---|---|---|---|\n")
DEPS_001_003 = "## Dependencies\n\n| ID | Blocks |\n|---|---|\n| 001 | 003 |\n\n"


def name(i):
    return f"ITM-{i}-SMP-Item{i}.md"


def title(i):
    return f"Sample item {i}"


def item(i, blocks="[]", drop=None):
    keys = {"id": i, "title": f'"{title(i)}"', "priority": "High", "status": "NOT_STARTED",
            "abbrev": "SMP", "created": "2024-01-01", "blocks": blocks}
    lines = ["---"] + [f"{k}: {v}" for k, v in keys.items() if k != drop]
    return "\n".join(lines + ["---", "", f"# {title(i)}", "", "Body text.", ""])


def row(i, blocks="", priority="High"):
    return f"| {i} | {title(i)} | {priority} | NOT_STARTED | 2024-01-01 | {blocks} | [{i}]({name(i)}) |\n"


def index(*rows, footer=FOOTER, deps=""):
    return f"# Backlog Index\n\n## Backlog Items\n\n{HEADER}{''.join(rows)}\n{deps}{footer}"


def project(tmp_path, index_text, items, files=None):
    planwise = tmp_path / "proj" / "planwise"
    backlog = planwise / "Backlog"
    (backlog / "Archive").mkdir(parents=True)
    for i, text in items.items():
        (backlog / name(i)).write_bytes(text.encode("utf-8"))
    (planwise / "config.yaml").write_bytes(b'project:\n  name: "test-project"\n  backlog_dir: "Backlog"\n'
                                           b'  index_files:\n    backlog: "00-Index-Backlog.md"\n')
    index_path = backlog / INDEX
    index_path.write_bytes(index_text.encode("utf-8"))
    for fname, data in (files or {}).items():
        (backlog / fname).write_bytes(data.encode("utf-8") if isinstance(data, str) else data)
    return planwise / "config.yaml", index_path


def snapshot(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*")
            if p.is_file() and ".git" not in p.parts}


def run(monkeypatch, capsys, config_path, *args):
    monkeypatch.setattr(sys, "argv", ["migrate_backlog_index.py", "--config", str(config_path), *args])
    code = mig.main()
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def git_commit(root):
    subprocess.run(["git", "init", "-q"], cwd=str(root), check=True)
    subprocess.run(["git", "add", "-A"], cwd=str(root), check=True)
    subprocess.run(["git", "-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-q", "-m", "init"],
                   cwd=str(root), check=True)


def part_name(k):
    naming = schema._index_naming(Path(INDEX))
    return schema._changelog_filename(naming) if k == 1 else sup.changelog_part_filename(naming, k)


def crash_on(target):
    def replace(src, dst):
        if Path(dst).name == target:
            raise OSError("simulated crash")
        os.replace(src, dst)
    return replace


def body_under(tokens, n_paras=1, nl="\n"):
    """A body of `n_paras` paragraphs whose `## Entry 1` section measures just under `tokens`."""
    size = int(tokens * 2.6 / n_paras)
    while True:
        para = ("padding words " * (size // 14 + 1))[:size].strip()
        body = (nl + nl).join(f"{para} {j}" for j in range(n_paras))
        measured = sup.changelog_tokens(f"## Entry 1{nl}{nl}{body}{nl}{nl}")
        if measured < tokens:
            return body, measured
        size -= 8


def grown_part1(nl="\n"):
    """An over-budget single changelog file: a two-paragraph ~24K-token entry and a small one."""
    half, _ = body_under(12000, nl=nl)
    return sup.changelog_text([f"{half}{nl}{nl}{half}".encode(), b"small two"], INDEX, nl)


# --- R3: a part's header plus its first chunk stays within budget --------

def test_r3_split_keeps_every_part_within_budget_at_real_scale():
    naming = schema._index_naming(Path(INDEX))
    body, measured = body_under(BUDGET - 5, n_paras=2)
    assert measured > BUDGET - 60, "setup must sit just under the budget"
    segments = [body.encode(), b"small second entry", body.encode()]
    result = sup.split_changelog(segments, naming, INDEX, "\n")
    assert len(result) > 1
    assert all(sup.changelog_tokens(text) < BUDGET for _n, text in result)
    assert sup.parse_changelog([text for _n, text in result]) == segments


def test_r3_unsplittable_first_entry_under_the_page_cap_is_kept_whole(tmp_path, monkeypatch, capsys):
    # The entry plus its part header reaches the warn budget but sits far under the page cap, so it keeps
    # its file whole and the ledger names it.
    body, _ = body_under(BUDGET - 20)
    footer = f"*Last Updated: 2024-01-01 — {body} Prior entry: 2023-12-01 — small entry.*\n"
    config_path, index_path = project(tmp_path, index(row("001"), footer=footer), {"001": item("001")})
    code, out, err = run(monkeypatch, capsys, config_path, NO_GIT, "--write")
    assert code == 0, err + out
    log = json.loads(mig.artifact_paths(index_path)[1].read_bytes().decode("utf-8"))
    [kept] = log["oversized_single_entries"]
    assert Path(kept["path"]).name == part_name(1) and BUDGET <= kept["tokens"] < sup.READ_PAGE_CAP_TOKENS
    assert log["changelog"]["unaccounted"] == 0 and log["verification"] == {"verified": True, "misses": []}
    assert body in (index_path.parent / part_name(1)).read_bytes().decode("utf-8")


# --- R5: a CRLF re-split writes CRLF only ----------------------------------

def test_r5_crlf_resplit_keeps_crlf_line_endings(tmp_path):
    _config, index_path = project(tmp_path, MIGRATED.replace("\n", "\r\n"), {},
                                  files={part_name(1): grown_part1("\r\n")})
    plan = sup.plan_changelog_resplit({}, index_path)
    assert plan is not None and len(plan["outputs"]) >= 2
    for _path, text in plan["outputs"]:
        assert text.count("\r\n") == text.count("\n") > 0


# --- R2: a re-split into fewer parts removes the parts it no longer uses ---

def test_r2_resplit_removes_parts_the_new_layout_no_longer_uses(tmp_path):
    half, _ = body_under(12000)
    names = [part_name(k) for k in range(1, 5)]
    parts_line = "Parts: " + ", ".join(f"[{n}]({n})" for n in names[1:])
    files = {names[0]: f"[← {INDEX}]({INDEX})\n\n{parts_line}\n\n## Entry 1\n\n{half}\n\n{half}\n\n"}
    for k in range(2, 5):
        files[names[k - 1]] = f"[← {names[0]}]({names[0]})\n\n## Entry {k}\n\nsmall entry {k}\n\n"
    _config, index_path = project(tmp_path, MIGRATED, {}, files=files)
    plan = mig.plan_changelog_resplit({}, index_path)
    mig.execute_outputs(plan["outputs"], plan["remove"])
    left = [index_path.with_name(n) for n in names if index_path.with_name(n).exists()]
    assert [p.name for p in left] == names[:len(plan["outputs"])] and len(left) < 4
    segments = sup.parse_changelog([p.read_bytes().decode("utf-8") for p in left])
    assert segments == [f"{half}\n\n{half}".encode(), b"small entry 2", b"small entry 3", b"small entry 4"]
    assert len(sup.changelog_budget_status({}, index_path)) == len(left)


# --- R4: a re-split refusal is REFUSED/exit 2, never a traceback -----------

def test_r4_split_changelog_refusal_exits_2(tmp_path, monkeypatch, capsys):
    grown = grown_part1() + "## Notes\n\nhand-added prose\n"
    config_path, _index = project(tmp_path, MIGRATED, {}, files={part_name(1): grown})
    code, out, err = run(monkeypatch, capsys, config_path, NO_GIT, "--split-changelog")
    assert code == 2 and "REFUSED" in err and "unrecognised section heading" in err, err + out


# --- R7: --split-changelog --write keeps the git gates ---------------------

def test_r7_split_changelog_write_refuses_without_git_state(tmp_path, monkeypatch, capsys):
    config_path, _index = project(tmp_path, MIGRATED, {}, files={part_name(1): grown_part1()})
    before = snapshot(tmp_path)
    code, out, err = run(monkeypatch, capsys, config_path, "--split-changelog", "--write")
    assert code == 2 and "cannot determine" in err and NO_GIT in err, err + out
    assert snapshot(tmp_path) == before


def test_r7_split_changelog_write_refuses_a_dirty_tree_without_force(tmp_path, monkeypatch, capsys):
    config_path, index_path = project(tmp_path, MIGRATED, {}, files={part_name(1): grown_part1()})
    git_commit(tmp_path / "proj")
    part1 = index_path.with_name(part_name(1))
    part1.write_bytes(part1.read_bytes() + b"## Entry 3\n\nhand edit\n\n")
    before = snapshot(tmp_path)
    code, out, err = run(monkeypatch, capsys, config_path, "--split-changelog", "--write")
    assert code == 2 and "uncommitted" in err, err + out
    assert snapshot(tmp_path) == before
    code, out, err = run(monkeypatch, capsys, config_path, "--split-changelog", "--write", "--force")
    assert code == 0, err + out


# --- R6: a header-only part 1 does not license overwriting Part-02 ---------

def test_r6_header_only_part1_does_not_overwrite_a_hand_written_part2(tmp_path, monkeypatch, capsys):
    filler = ("padding text for a large changelog entry " * 600)[:22000]
    footer = "*Last Updated: " + " Prior entry: ".join(f"2024-0{i + 1}-01 — {filler} #{i}" for i in range(3)) + "*\n"
    files = {part_name(1): f"[← {INDEX}]({INDEX})\n", part_name(2): "hand-written notes\n"}
    config_path, _index = project(tmp_path, index(row("001"), footer=footer), {"001": item("001")}, files=files)
    before = snapshot(tmp_path)
    code, out, err = run(monkeypatch, capsys, config_path, NO_GIT, "--write")
    assert code == 2 and part_name(2) in err, err + out
    assert snapshot(tmp_path) == before


# --- R10: --report recognises an interrupted multi-part migration ----------

def test_r10_report_calls_an_interrupted_multi_part_changelog_populated(tmp_path, monkeypatch, capsys):
    filler = ("padding text for a large changelog entry " * 600)[:22000]
    footer = "*Last Updated: " + " Prior entry: ".join(f"2024-0{i + 1}-01 — {filler} #{i}" for i in range(3)) + "*\n"
    config_path, index_path = project(tmp_path, index(row("001"), footer=footer), {"001": item("001")})
    monkeypatch.setattr(sup, "_replace", crash_on(INDEX))
    assert run(monkeypatch, capsys, config_path, NO_GIT, "--write")[0] == 1
    monkeypatch.undo()
    assert index_path.with_name(part_name(2)).exists()
    code, out, err = run(monkeypatch, capsys, config_path, "--report")
    assert code == 0, err + out
    assert json.loads(out)["changelog"] == "populated"


# --- R8: a rerun resumes after a replace interrupted mid-way ---------------

def test_r8_rerun_resumes_after_an_item_file_was_already_replaced(tmp_path, monkeypatch, capsys):
    items = {i: item(i, drop="created") for i in ("001", "002")}
    config_path, _index = project(tmp_path, index(row("001"), row("002")), items)
    git_commit(tmp_path / "proj")
    monkeypatch.setattr(sup, "_replace", crash_on(name("002")))
    assert run(monkeypatch, capsys, config_path, "--write", "--backfill-frontmatter")[0] == 1
    monkeypatch.undo()
    code, out, err = run(monkeypatch, capsys, config_path, "--write", "--backfill-frontmatter")
    assert code == 0, err + out
    assert json.loads(mig.artifact_paths(_index)[1].read_bytes())["mode"] == "write"


# --- R1: index-wins unions a Dependencies edge instead of dropping it ------

def test_index_wins_unions_a_dependencies_edge(tmp_path, monkeypatch, capsys):
    items = {i: item(i) for i in ("001", "002", "003")}
    text = index(row("001", blocks="002"), row("002"), row("003"), deps=DEPS_001_003)
    config_path, index_path = project(tmp_path, text, items)
    code, out, err = run(monkeypatch, capsys, config_path, NO_GIT, "--write", "--write-edges",
                         "--reconcile", "index-wins")
    assert code == 0, err + out
    assert "blocks: [002, 003]" in (index_path.parent / name("001")).read_text(encoding="utf-8")
    edges = json.loads(mig.artifact_paths(index_path)[1].read_bytes())["edges"]
    assert edges == [{"src": "001", "dst": "003", "source": "dependencies-table"}]
    cells = json.loads(mig.artifact_paths(index_path)[1].read_bytes())["reconcile"]["cells"]
    assert [(c["index"], c["written"]) for c in cells] == [(["002"], ["002", "003"])]
    # the check is exact: a written list that differs from the planned union is a miss
    item_path = index_path.parent / name("001")
    stale = {"changelog": {"segments": [], "parts": [(index_path, None)]}, "dests": [],
             "reconcile": {"mode": "index-wins", "cells": [{**cells[0], "path": item_path, "written": ["002", "004"]}]},
             "index_text": index_path.read_text(encoding="utf-8")}
    misses = mig.verify_written(stale, mig.artifact_paths(index_path), index_path)
    assert [m for m in misses if m.startswith("reconciled blocks: [002, 004]")]


# --- L5, L6, L4 -------------------------------------------------------------

def test_l5_index_wins_names_an_empty_cell_instead_of_writing_an_empty_key(tmp_path, monkeypatch, capsys):
    config_path, _index = project(tmp_path, index(row("001", priority="")), {"001": item("001")})
    code, out, err = run(monkeypatch, capsys, config_path, NO_GIT, "--reconcile", "index-wins")
    assert code == 2 and "cannot settle" in err, err + out


def test_l6_header_only_changelog_with_a_bom_counts_as_absent(tmp_path, monkeypatch, capsys):
    files = {part_name(1): "﻿" + f"[← {INDEX}]({INDEX})\n"}
    config_path, _index = project(tmp_path, index(row("001")), {"001": item("001")}, files=files)
    code, out, err = run(monkeypatch, capsys, config_path, NO_GIT, "--write")
    assert code == 0, err + out


def test_l4_replace_key_line_replaces_an_unindented_block_list():
    text = "---\nid: 001\nblocks:\n- 002\n- 004\n---\n\nbody\n"
    assert repairs.replace_key_line(text, "blocks", "[002, 003]") == "---\nid: 001\nblocks: [002, 003]\n---\n\nbody\n"


# --- S3: a large relocated entry verifies, and one at the page cap is refused -

PREAMBLE_LINE = "Preamble note number {:05d} about something the team once wrote down here."


def preamble_index(n):
    """An index whose lines 3 to n + 2 are preamble text the migration relocates."""
    pre = "".join(PREAMBLE_LINE.format(i) + "\n" for i in range(n))
    return index(row("001")).replace("# Backlog Index\n\n", f"# Backlog Index\n\n{pre}\n", 1)


def relocated_tokens(n):
    records = [{"line": i + 3, "kind": "preamble", "text": PREAMBLE_LINE.format(i)} for i in range(n)]
    return sup.changelog_tokens(f"## Entry 1\n\n{reloc.render_relocated_entry(records, '2024-01-01')}\n\n")


def changelog_texts(index_path):
    return [p.read_bytes().decode("utf-8") for p in sorted(index_path.parent.glob("00-Changelog-Backlog*.md"))]


def test_s3_a_relocated_entry_split_at_its_paragraph_verifies(tmp_path, monkeypatch, capsys):
    assert BUDGET <= relocated_tokens(600) < sup.READ_PAGE_CAP_TOKENS, "setup must reach the paragraph split"
    config_path, index_path = project(tmp_path, preamble_index(600), {"001": item("001")})
    code, out, err = run(monkeypatch, capsys, config_path, NO_GIT, "--write")
    texts = changelog_texts(index_path)
    assert any("## Entry 1 (continued)" in text for text in texts), texts[0][:300]
    assert code == 0, err + out
    log = json.loads(mig.artifact_paths(index_path)[1].read_bytes().decode("utf-8"))
    assert log["changelog"]["unaccounted"] == 0 and log["verification"] == {"verified": True, "misses": []}
    assert all(f"(preamble): {PREAMBLE_LINE.format(i)}\n" in "".join(texts) for i in range(600))


def test_s3_a_relocated_entry_at_the_page_cap_is_refused_before_any_write(tmp_path, monkeypatch, capsys):
    assert relocated_tokens(700) >= sup.READ_PAGE_CAP_TOKENS, "setup must reach the page cap"
    config_path, _index = project(tmp_path, preamble_index(700), {"001": item("001")})
    before = snapshot(tmp_path)
    code, out, err = run(monkeypatch, capsys, config_path, NO_GIT, "--write")
    assert code == 2 and "REFUSED" in err, err + out
    fix = err.strip().rsplit(" -- ", 1)[1]
    assert "index lines 3-702" in fix and "entry" not in fix.lower(), fix
    assert snapshot(tmp_path) == before


# --- S4: a '## Dependencies' row note keeps the targets it was written beside --

def deps(row_text):
    return f"## Dependencies\n\n| ID | Blocks |\n|---|---|\n{row_text}\n\n"


def test_s4_a_dependencies_row_note_keeps_its_targets(tmp_path, monkeypatch, capsys):
    text = index(row("001", blocks="002, 003"), row("002"), row("003"),
                 deps=deps("| 001 | 002, 003 (only once the `API` lands) |"))
    items = {"001": item("001", blocks="[002, 003]"), "002": item("002"), "003": item("003")}
    config_path, index_path = project(tmp_path, text, items)
    code, out, err = run(monkeypatch, capsys, config_path, NO_GIT, "--write", "--extract-dependency-notes")
    assert code == 0, err + out
    body = (index_path.parent / name("001")).read_bytes().decode("utf-8")
    assert body.split(sup.NOTES_HEADING_DEPS)[1].strip() == "- 002, 003: only once the `API` lands"


@pytest.mark.parametrize("cell,note", [
    ("002 (needs the  `selector`)", "needs the  `selector`"),
    ("002 (see [the design](Archive/d.md) first)", "see [the design](Archive/d.md) first"),
], ids=["code-span-and-double-space", "link"])
def test_s4_a_dependencies_note_is_the_cells_own_text(cell, note):
    assert sup.dependency_cell_parts(cell) == ([(None, "002")], note)


# --- L5, L7: id prefixes in a Blocks cell and in the '## Dependencies' table --

def prow(cell_id, i, blocks=""):
    """An items-table row whose ID cell reads `cell_id`."""
    return f"| {cell_id} | {title(i)} | High | NOT_STARTED | 2024-01-01 | {blocks} | [{i}]({name(i)}) |\n"


ACCEPTED_PREFIXES = [
    # controls: the items table's own prefix in a Blocks cell, in either case
    ("blocks-own-prefix", index(prow("ITM-001", "001", "ITM-002"), prow("ITM-002", "002")), "[002]", ()),
    ("blocks-own-prefix-lower-case", index(prow("ITM-001", "001", "itm-002"), prow("ITM-002", "002")), "[002]", ()),
    ("deps-lower-case", index(prow("ITM-001", "001", "ITM-002"), prow("ITM-002", "002"),
                              deps=deps("| itm-001 | itm-002 |")), "[002]", ()),
    ("deps-prefix-from-a-later-row", index(prow("001", "001", "002"), prow("ITM-002", "002"),
                                           deps=deps("| 001 | ITM-002 |")), "[002]", ()),
]


@pytest.mark.parametrize("text,blocks,args", [pytest.param(*r[1:], id=r[0]) for r in ACCEPTED_PREFIXES])
def test_l7_the_items_prefix_matches_in_any_case_and_from_any_row(tmp_path, monkeypatch, capsys, text, blocks, args):
    config_path, index_path = project(tmp_path, text, {"001": item("001", blocks=blocks), "002": item("002")})
    code, out, err = run(monkeypatch, capsys, config_path, NO_GIT, "--write", *args)
    assert code == 0, err + out
    assert "blocks: [002]" in (index_path.parent / name("001")).read_bytes().decode("utf-8")


def test_l7_mixed_items_prefixes_are_all_named_in_the_foreign_prefix_fix(tmp_path, monkeypatch, capsys):
    text = index(prow("ABC-001", "001"), prow("ITM-002", "002"), deps=deps("| XYZ-001 | 002 |"))
    config_path, _index = project(tmp_path, text, {"001": item("001"), "002": item("002")})
    before = snapshot(tmp_path)
    code, out, err = run(monkeypatch, capsys, config_path, NO_GIT, "--write", "--write-edges")
    assert code == 2 and "uses a prefix other than the items table's" in err, err + out
    assert "(the items table writes ABC- or ITM-)" in err, err
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("args", [(), ("--write-edges",)], ids=["no-flags", "write-edges"])
def test_l7_a_self_edge_is_refused_with_its_own_fix(tmp_path, monkeypatch, capsys, args):
    config_path, _index = project(tmp_path, index(row("001"), deps=deps("| 001 | 001 |")), {"001": item("001")})
    before = snapshot(tmp_path)
    code, out, err = run(monkeypatch, capsys, config_path, NO_GIT, "--write", *args)
    assert code == 2 and "names its own item 001 as a blocker" in err, err + out
    assert "001<->001" not in err and "001 blocks 001" not in err, err
    assert snapshot(tmp_path) == before
