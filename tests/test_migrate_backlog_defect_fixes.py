"""Regression tests for five migration defects a real hand-authored backlog
exposed: a misparsed Abbrev cell winning under `--reconcile index-wins`, a
bold heading with a trailing parenthetical refused as prose, an abbrev
refusal that named the wrong cause, a prefixed `id:` value the generator
cannot read, and an empty Created cell counted as a disagreement. Fixtures
are written as bytes under tmp_path, never under plugins/planwise/, and use
sample prefixes and ids only."""
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import backlog_migration as bm
import migrate_backlog_checks as chk
import migrate_backlog_index as mig
import migrate_backlog_repairs as repairs
import migrate_backlog_support as sup
from config_gen import InitConfig

NO_GIT = "--allow-untracked-tree"
ALL_FLAGS = ("--backfill-frontmatter", "--write-edges", "--extract-dependency-notes", "--reconcile", "index-wins")
HEADER = "| ID | Feature | Priority | Status | Abbrev | Created | Files |\n|---|---|---|---|---|---|---|\n"
FOOTER = "*Last Updated: 2024-01-01 — did something. Prior entry: 2023-12-01 — did something else.*\n"
CONFIG = ('project:\n  name: "test-project"\n  backlog_dir: "Backlog"\n  index_files:\n'
          '    backlog: "00-Index-Backlog.md"\nabbreviations:\n  BUG: Bug fixes\n  SMP: Sample work\n')
REAL_HEADING = "**Soft dependencies** (informational, not enforced by scoring):"
NEAR_MISS = "**Note** this row moved to 004."


def fm(item_id, abbrev="BUG", drop=()):
    keys = {"id": item_id, "title": '"Sample item"', "priority": "High", "status": "NOT_STARTED",
            "abbrev": abbrev, "created": "2024-01-01", "blocks": "[]"}
    return "\n".join(["---"] + [f"{k}: {v}" for k, v in keys.items() if k not in drop] + ["---", ""]) + "\n"


def row(item_id, name, abbrev="BUG", created="2024-01-01"):
    return f"| {item_id} | Sample item | High | NOT_STARTED | {abbrev} | {created} | [{item_id}]({name}) |\n"


def index(*rows, deps=""):
    return f"# Backlog Index\n\n## Backlog Items\n\n{HEADER}{''.join(rows)}\n{deps}{FOOTER}"


def project(tmp_path, index_text, items, config=CONFIG):
    """items: {file name: text}. Returns (config path, index path)."""
    planwise = tmp_path / "proj" / "planwise"
    backlog = planwise / "Backlog"
    (backlog / "Archive").mkdir(parents=True)
    for name, text in items.items():
        (backlog / name).write_bytes(text.encode("utf-8"))
    (planwise / "config.yaml").write_bytes(config.encode("utf-8"))
    index_path = backlog / "00-Index-Backlog.md"
    index_path.write_bytes(index_text.encode("utf-8"))
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


def frontmatter(path):
    return repairs.partial_frontmatter(path.read_bytes().decode("utf-8"))[0]


# --- A: a misparsed Abbrev cell never wins ------------------------------------

@pytest.mark.parametrize("head", ["", fm("001", drop=("created",))], ids=["no-block", "partial-block"])
def test_a_misparsed_abbrev_cell_keeps_the_filename_segment_under_index_wins(tmp_path, monkeypatch, capsys, head):
    name = "ITM-001-BUG-First.md"
    config_path, index_path = project(tmp_path, index(row("001", name, abbrev="0")), {name: head + "# First\n"})
    code, out, err = run(monkeypatch, capsys, config_path, *ALL_FLAGS, "--write")
    assert code == 0, err + out
    assert frontmatter(index_path.parent / name)["abbrev"] == "BUG"
    assert [c for c in ledger(index_path)["reconcile"]["cells"] if c["key"] == "abbrev"] == []


def test_a_configured_abbrev_cell_still_reconciles(tmp_path, monkeypatch, capsys):
    """Control: an Abbrev cell that IS a configured abbreviation still wins under index-wins."""
    name = "ITM-001-BUG-First.md"
    config_path, index_path = project(tmp_path, index(row("001", name, abbrev="SMP")), {name: fm("001") + "# First\n"})
    code, out, err = run(monkeypatch, capsys, config_path, *ALL_FLAGS, "--write")
    assert code == 0, err + out
    assert frontmatter(index_path.parent / name)["abbrev"] == "SMP"
    assert ledger(index_path)["reconcile"]["cells"] == [
        {"id": "001", "key": "abbrev", "frontmatter": "BUG", "index": "SMP"}]


@pytest.mark.parametrize("cell,valid,expected", [
    ("0", {"BUG"}, []), ("", {"BUG"}, []), ("0", None, []),
    ("SMP", {"BUG", "SMP"}, ["abbrev"]), ("SMP", None, ["abbrev"]),
    # No abbreviations configured: a lowercase cell is still a value, so it disagrees by name
    # instead of being skipped; the migrator later refuses to write it as an abbrev.
    ("core", None, ["abbrev"]),
])
def test_a_row_diffs_treats_an_unusable_abbrev_cell_as_no_value(cell, valid, expected):
    roles = {"id": 0, "feature": 1, "abbrev": 2, "file": 3}
    fields = {"id": "001", "abbrev": "BUG", "_path": Path("ITM-001-BUG-First.md")}
    diffs = sup.row_diffs(["001", "Sample item", cell, "[001](x.md)"], roles, fields, valid)
    assert [d["key"] for d in diffs] == expected


@pytest.mark.parametrize("cell", ["DOC", "XYZ"])
def test_a_row_diffs_refuses_an_abbrev_shaped_cell_that_is_not_configured(cell):
    # Skipping it would let an index-wins regeneration erase the cell's value without a word.
    roles = {"id": 0, "feature": 1, "abbrev": 2, "file": 3}
    fields = {"id": "001", "abbrev": "BUG", "_path": Path("ITM-001-BUG-First.md")}
    with pytest.raises(sup.Refusal, match=rf"Abbrev cell {cell} is not in config.yaml abbreviations: -- add {cell} "):
        sup.row_diffs(["001", "Sample item", cell, "[001](x.md)"], roles, fields, {"BUG"})


def test_a_unconfigured_abbrev_cell_refuses_the_whole_run_and_writes_nothing(tmp_path, monkeypatch, capsys):
    name = "ITM-001-BUG-First.md"
    config_path, _ = project(tmp_path, index(row("001", name, abbrev="XYZ")), {name: fm("001") + "# First\n"})
    before = snapshot(tmp_path)
    code, out, err = run(monkeypatch, capsys, config_path, *ALL_FLAGS, "--write")
    assert code == 2, err + out
    assert "Abbrev cell XYZ is not in config.yaml abbreviations" in err
    assert snapshot(tmp_path) == before


def test_a_lowercase_abbrev_cell_with_no_config_is_refused_by_name_not_erased(tmp_path, monkeypatch, capsys):
    name = "ITM-001-BUG-First.md"
    no_abbrevs = CONFIG.split("abbreviations:")[0]
    config_path, _ = project(tmp_path, index(row("001", name, abbrev="core")),
                             {name: fm("001") + "# First\n"}, config=no_abbrevs)
    before = snapshot(tmp_path)
    code, out, err = run(monkeypatch, capsys, config_path, *ALL_FLAGS, "--write")
    assert code == 2, err + out
    assert "would write abbrev: 'core'" in err
    assert snapshot(tmp_path) == before


def test_a_the_migrator_refuses_to_write_an_unconfigured_abbrev(tmp_path):
    path = tmp_path / "ITM-001-BUG-First.md"
    path.write_bytes((fm("001") + "# First\n").encode("utf-8"))
    planned = {path: fm("001", abbrev="0") + "# First\n"}
    with pytest.raises(mig.Refusal, match=r"would write abbrev: '0'.*add it to abbreviations: in config.yaml"):
        mig._refuse_unusable_abbrevs(planned, {"BUG"})
    mig._refuse_unusable_abbrevs({path: fm("001", abbrev="BUG") + "# Changed body\n"}, {"BUG"})


# --- B: a bold heading with a parenthetical is structural ---------------------

def test_b_bold_heading_with_a_parenthetical_is_structural_and_prose_is_still_reported():
    assert repairs._BOLD_HEADING_RE.match(REAL_HEADING)
    assert repairs._BOLD_HEADING_RE.match("**Soft dependencies**")
    assert not repairs._BOLD_HEADING_RE.match(NEAR_MISS)
    assert not repairs._BOLD_HEADING_RE.match("**Note** (moved) and more text")
    text = (f"# Backlog Index\n\n## Backlog Items\n\n{HEADER}\n## Dependencies\n\n{REAL_HEADING}\n\n"
            f"- 002 relates to 001\n\n{NEAR_MISS}\n\n{FOOTER}")
    problems, _edges, found = chk.scan_index(text, text.split("\n").index(HEADER.split("\n")[0]), True)
    assert [f["text"] for f in found if f["kind"] == "heading"] == [REAL_HEADING]
    assert [f["owner"] for f in found if f["kind"] == "bullet"] == ["002"]
    assert len(problems) == 1 and "Note** this row moved to 004" in problems[0]


# --- C: an unconfigured abbrev names config.yaml -------------------------------

@pytest.mark.parametrize("cell", ["PROC", ""], ids=["cell-and-name", "name-only"])
def test_c_unconfigured_abbrev_refusal_names_config_yaml(tmp_path, monkeypatch, capsys, cell):
    name = "ITM-001-PROC-First.md"
    config_path, _ = project(tmp_path, index(row("001", name, abbrev=cell)), {name: "# First\n"})
    before = snapshot(tmp_path)
    code, out, err = run(monkeypatch, capsys, config_path, *ALL_FLAGS, "--force", "--write")
    assert code == 2, err + out
    assert "abbrev PROC is not in config.yaml abbreviations:" in err, err
    assert "add PROC to abbreviations: in config.yaml" in err, err
    assert "no such column" not in err
    assert snapshot(tmp_path) == before


# --- D: a prefixed id: value is normalised, or refused --------------------------

@pytest.mark.parametrize("name,value", [("ITM-001-01-BUG-First.md", "ITM-001"),
                                        ("ITM-001-01-BUG-First.md", "ITM-001-01"),
                                        ("ITM-001-BUG-First.md", '"ITM-001"')])
def test_d_bare_id_accepts_only_a_value_naming_its_file_and_row(name, value):
    assert repairs.bare_id(value, name, "001") == "001"
    assert repairs.bare_id("001", name, "001") is None


@pytest.mark.parametrize("name,value,row_id,fragment", [
    ("ITM-001-BUG-First.md", "XYZ-001", "001", "file name"),
    ("ITM-001-BUG-First.md", "ITM-002", "001", "file name"),
    ("ITM-001-01-BUG-First.md", "ITM-001-02", "001", "file name"),
    ("ITM-001-BUG-First.md", "ITM-001", "002", "index row"),
    ("ITM-001-BUG-First.md", "ITM-001", None, "no single index row"),
    ("First.md", "ITM-001", "001", "no leading"),
])
def test_d_bare_id_refuses_a_value_that_does_not_name_its_file(name, value, row_id, fragment):
    with pytest.raises(ValueError, match=fragment):
        repairs.bare_id(value, name, row_id)


def test_d_prefixed_id_is_normalised_with_a_backup_and_a_ledger_entry(tmp_path):
    name = "ITM-001-01-BUG-First.md"
    original = fm("ITM-001-01", drop=("created",)) + "# First\n"
    config_path, index_path = project(tmp_path, index(row("001", name)), {name: original})
    cfg = InitConfig(project_name="test-project", project_root=config_path.parent.parent, plugin_root=SCRIPTS.parent)
    report = bm.migrate_backlog_if_legacy(cfg, "1.0", "1.1")
    assert report.state == "migrated", report.detail
    item = index_path.parent / name
    assert frontmatter(item)["id"] == "001"
    assert item.read_bytes().decode("utf-8").startswith("---\nid: 001\ntitle:")
    assert (report.backup_dir / name).read_bytes() == original.encode("utf-8")
    assert any(Path(w).name == name for w in report.written)
    repaired = json.loads(report.ledger_path.read_bytes().decode("utf-8"))["id_repairs"]
    assert [(Path(r["path"]).name, r["from"], r["to"]) for r in repaired] == [(name, "ITM-001-01", "001")]


def test_d_mismatched_prefixed_id_refuses_naming_the_file(tmp_path, monkeypatch, capsys):
    name = "ITM-001-BUG-First.md"
    config_path, _ = project(tmp_path, index(row("001", name)), {name: fm("XYZ-001") + "# First\n"})
    before = snapshot(tmp_path)
    code, out, err = run(monkeypatch, capsys, config_path, *ALL_FLAGS, "--force", "--write")
    assert code == 2 and name in err and "fix its id: line by hand" in err, err + out
    assert snapshot(tmp_path) == before


def test_d_prefixed_id_without_the_flag_names_the_flag(tmp_path, monkeypatch, capsys):
    name = "ITM-001-BUG-First.md"
    config_path, _ = project(tmp_path, index(row("001", name)), {name: fm("ITM-001") + "# First\n"})
    code, out, err = run(monkeypatch, capsys, config_path, "--force", "--write")
    assert code == 2 and "non-numeric id value" in err and "add --backfill-frontmatter" in err, err + out


# --- E: an empty Created cell supplies no value --------------------------------

def test_e_empty_created_cell_is_no_disagreement(tmp_path, monkeypatch, capsys):
    name = "ITM-001-BUG-First.md"
    config_path, index_path = project(tmp_path, index(row("001", name, created="")), {name: fm("001") + "# First\n"})
    code, out, err = run(monkeypatch, capsys, config_path, "--write")
    assert code == 0, err + out
    assert frontmatter(index_path.parent / name)["created"] == "2024-01-01"
    assert ledger(index_path)["reconcile"]["cells"] == []


# --- Review fixes ----------------------------------------------------------------

PAREN_PROSE = "**Blocked by** (012 must ship before 015; do not reorder):"
INDENTED_BOLD = "  **Why** (the design review said the schema lands first):"


@pytest.mark.parametrize("line", [
    PAREN_PROSE, INDENTED_BOLD, "  **Soft dependencies**", "**Why** (the schema lands first. Then the API):",
    "**Why** (see item 012)", "**Why** (first; second)",
])
def test_w1_a_bold_line_with_an_id_a_sentence_or_an_indent_is_not_a_heading(line):
    assert not repairs._BOLD_HEADING_RE.match(line)


@pytest.mark.parametrize("line", [REAL_HEADING, "**Soft dependencies**", "**Notes** (see below.):"])
def test_w1_a_plain_bold_heading_is_still_structural(line):
    assert repairs._BOLD_HEADING_RE.match(line)


def test_w1_neither_review_line_is_dropped_silently():
    bullet = "- 012 relates to 015 because the API is shared"
    deps = f"## Dependencies\n\n{bullet}\n{INDENTED_BOLD}\n\n{PAREN_PROSE}\n\n"
    text = index(deps=deps)
    problems, _edges, found = chk.scan_index(text, text.split("\n").index(HEADER.split("\n")[0]), True)
    assert [f for f in found if f["kind"] == "heading"] == []
    [note] = [f for f in found if f["kind"] == "bullet"]
    assert note["text"] == f"{bullet}\n{INDENTED_BOLD}" and note["count"] == 2  # carried with its bullet
    assert len(problems) == 1 and "Blocked by** (012 must ship" in problems[0]  # reported, never dropped


def test_n1_a_parked_unit_missing_from_disk_is_unaccounted_and_fails_the_write(tmp_path, monkeypatch):
    # The plan's own buckets still balance; only the re-read from disk can see the unit is nowhere.
    name = "ITM-001-BUG-First.md"
    unit = "Alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima mike."
    body = "Alpha bravo charlie delta echo foxtrot golf then something unrelated follows.\n"
    config_path, _ = project(tmp_path, index(row("001", name).replace("| Sample item |", f"| Sample item. {unit} |")),
                             {name: fm("001") + body})
    cfg = InitConfig(project_name="test-project", project_root=config_path.parent.parent, plugin_root=SCRIPTS.parent)
    monkeypatch.setattr(mig, "parked_records", lambda dests: [])
    report = bm.migrate_backlog_if_legacy(cfg, "1.0", "1.1")
    assert report.state == "write_failed", report.detail
    assert "1 row prose unit(s)" in report.detail and "neither in an item file nor parked" in report.detail
    assert "the tree was restored" in report.detail


def test_n1_the_ledger_accounting_is_derived_from_disk(tmp_path, monkeypatch, capsys):
    name = "ITM-001-BUG-First.md"
    config_path, index_path = project(tmp_path, index(row("001", name)), {name: fm("001") + "# First\n"})
    code, out, err = run(monkeypatch, capsys, config_path, "--write")
    assert code == 0, err + out
    assert ledger(index_path)["dedup"]["unaccounted_basis"] == "re-read from disk"


@pytest.mark.parametrize("flags", [(), ALL_FLAGS], ids=["no-flags", "all-flags"])
def test_n2_a_prefixed_blocks_entry_is_named_and_not_sent_to_backfill(tmp_path, monkeypatch, capsys, flags):
    name = "ITM-001-BUG-First.md"
    config_path, _ = project(tmp_path, index(row("001", name)),
                             {name: fm("001").replace("blocks: []", "blocks: [ITM-002]") + "# First\n"})
    code, out, err = run(monkeypatch, capsys, config_path, *flags, "--force", "--write")
    assert code == 2, err + out
    assert f"{name} has blocks: entry 'ITM-002'" in err and "does not rewrite blocks: entries" in err, err
    assert "add --backfill-frontmatter" not in err


# Suffix 03 on id 012: a digit-run reading of "012-03" finds two ids (012 and 003), not one.
@pytest.mark.parametrize("cell", ["012-03", "ITM-012-03"])
def test_n3_a_suffixed_row_id_normalises_when_prefix_number_and_suffix_agree(tmp_path, cell):
    name = "ITM-012-03-BUG-First.md"
    config_path, index_path = project(tmp_path, index(row(cell, name)), {name: fm("ITM-012-03") + "# First\n"})
    cfg = InitConfig(project_name="test-project", project_root=config_path.parent.parent, plugin_root=SCRIPTS.parent)
    report = bm.migrate_backlog_if_legacy(cfg, "1.0", "1.1")
    assert report.state == "migrated", report.detail
    assert frontmatter(index_path.parent / name)["id"] == "012"


@pytest.mark.parametrize("cell,fragment", [("012-04", "suffix '04'"), ("XYZ-012-03", "prefix 'XYZ'")])
def test_n3_a_suffixed_row_id_that_disagrees_is_refused_by_name(tmp_path, cell, fragment):
    name = "ITM-012-03-BUG-First.md"
    config_path, _ = project(tmp_path, index(row(cell, name)), {name: fm("ITM-012-03") + "# First\n"})
    cfg = InitConfig(project_name="test-project", project_root=config_path.parent.parent, plugin_root=SCRIPTS.parent)
    before = snapshot(tmp_path)
    report = bm.migrate_backlog_if_legacy(cfg, "1.0", "1.1")
    assert report.state == "refused" and name in report.detail and fragment in report.detail, report.detail
    assert snapshot(tmp_path) == before
