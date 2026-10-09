#!/usr/bin/env python3
"""Tests for `migrate_plans_index.py`: the standalone plans-index migrator.

Every fixture is built as bytes under `tmp_path` (never `write_text`), so a
line-ending rewrite shows up as a byte difference. Nothing here reads or
writes the live project. Each behaviour has a producing test and a
non-producing control.

Run with:  python -m pytest tests/test_migrate_plans_index.py -q
"""

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import config_loader
import generate_plans_index as gen
import migrate_plans_index as mig
from reconcile_common import read_text_preserving_newlines as read_text

DATE = "2026-10-01"
CONFIG = b"plans_dir: Plans\nproject:\n  index_files:\n    plans: 00-Index-Plans.md\n"
SEED_LF = (
    "# Plans Index\n\n| Abbrev | Name | Status | Created | Last Updated | Path |\n"
    "|--------|------|--------|---------|--------------|------|\n\n## Status Legend\n\n"
    "| Status | Meaning |\n|--------|---------|\n"
    "| NOT_STARTED | Plan created but no work begun |\n"
    "| PLANNING | Discovery or session planning in progress |\n"
    "| IN_PROGRESS | Active execution underway |\n"
    "| BLOCKED | Waiting on external dependency |\n"
    "| COMPLETE | All sprints and sessions finished |\n"
    "| CLOSED | Archived — no further work expected |\n"
)
BANNER = (
    "> [!note] Historical notes moved from the plans index on {date}, each attached to the row it followed "
    "in the index. They record what was true when written; this Master Plan's **Status:** line is authoritative."
)
ALP = "| ALP | Alpha | COMPLETE | 2026-01-10 | 2026-01-20 | Alpha/ |"
BET = "| BET | Beta | IN_PROGRESS | 2026-02-01 | 2026-02-10 | Beta/ |"
GAM = "| GAM | Gamma | IN_PROGRESS Sprint 2 of 3 running | 2026-03-01 | 2026-03-05 | Gamma/ |"


@pytest.fixture(autouse=True)
def pin_today(monkeypatch):
    monkeypatch.setattr(mig, "_today", lambda: DATE)


def legacy_index(inserted, nl="\r\n", seed=SEED_LF, tail=""):
    """The seed with `inserted` lines after its separator row, in `nl`, as bytes."""
    lines = seed.split("\n")[:-1]
    lines[4:4] = inserted
    return (nl.join(lines) + nl + tail.replace("\n", nl)).encode("utf-8")


def master_plan(title, status, created, updated, nl="\n", eol=True):
    lines = [f"# {title} Master Plan", "", f"**Status:** {status}", f"**Created:** {created}", "", "Body.", "",
             f"*Last Updated: {updated}*"]
    return (nl.join(lines) + (nl if eol else "")).encode("utf-8")


def build(tmp_path, index, plans):
    """Write a project. Returns `(config, plans_dir, index_path)`."""
    planwise = tmp_path / "proj" / "planwise"
    (planwise / "Plans").mkdir(parents=True, exist_ok=True)
    (planwise / "config.yaml").write_bytes(CONFIG)
    for rel, data in plans.items():
        target = planwise / "Plans" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    index_path = planwise / "Plans" / "00-Index-Plans.md"
    if index is not None:
        index_path.write_bytes(index)
    config = config_loader.load_config(SCRIPTS / "x.py", config_path=planwise / "config.yaml")
    return config, config["_plans_dir"], config["_plans_index"]


A_PLANS = {
    "Alpha/ALP-Master-Plan.md": master_plan("Alpha", "COMPLETE", "2026-01-10", "2026-01-20", "\r\n"),
    "Beta/BET-Master-Plan.md": master_plan("Beta", "IN_PROGRESS", "2026-02-01", "2026-02-10"),
    "Gamma/GAM-Master-Plan.md": master_plan("Gamma", "COMPLETE", "2026-03-01", "2026-03-05", eol=False),
}
A_COMMENT = "<!-- BET: waiting on the vendor review before Sprint 3 -->"


def fixture_a(tmp_path):
    return build(tmp_path, legacy_index([ALP, BET, A_COMMENT, GAM]), A_PLANS)


B_PLANS = {
    "Alpha/Meta-ALP/ALP-META-Master-Plan.md": master_plan("Alpha", "COMPLETE", "2026-01-05", "2026-01-08"),
    "Alpha/Exec-ALP/ALP-Master-Plan.md": master_plan("Alpha", "COMPLETE", "2026-01-10", "2026-01-20"),
    "Beta/Meta-BET/BET-META-Master-Plan.md": master_plan("Beta", "IN_PROGRESS", "2026-02-01", "2026-02-10"),
    "Gamma/GAM-Master-Plan.md": master_plan("Gamma", "✅ **COMPLETE** — closed 2026-03-05",
                                            "2026-03-01", "2026-03-05"),
}
B_LINES = [
    "| ALP | Alpha | COMPLETE | 2026-01-10 | 2026-01-20 | Plans/Alpha/ |",
    "<!-- ALP: the Exec scaffold finished; Meta notes are in the Meta plan -->",
    "| BET | Beta | IN_PROGRESS | 2026-02-01 | 2026-02-10 | Plans/Beta/ |",
    "<!-- BET: Discovery only, no Exec plan yet -->",
    "| GAM | Gamma | **✅** | 2026-03-01 | 2026-03-05 | Plans/Gamma/ |",
    "<!-- GAM: closed after one sprint -->",
]


def fixture_b(tmp_path):
    return build(tmp_path, legacy_index(B_LINES), B_PLANS)


C_PLANS = {
    "One/ONE-Master-Plan.md": master_plan("One", "IN_PROGRESS", "2026-01-10", "2026-01-20"),
    "Three/THR-Master-Plan.md": master_plan("Three", "IN_PROGRESS", "2026-03-01", "2026-03-05", "\r\n"),
}
TWO = "| TWO | Two | IN_PROGRESS | 2026-02-01 | 2026-02-10 | Two/ |"
C_LINES = [
    "<!-- C1: before any row -->",
    "| ONE | One | IN_PROGRESS | 2026-01-10 | 2026-01-20 | One/ |",
    "<!-- C2: first note on ONE -->",
    "<!-- C3: second note on ONE -->",
    "<!-- C4: third note on ONE -->",
    TWO,
    "<!-- C5: after a row whose Master Plan is missing -->",
    "| THR | Three | IN_PROGRESS | 2026-03-01 | 2026-03-05 | Three/ |",
    "<!-- C6: a note that",
    "spans two lines -->",
    "<!-- C7: orphan at the tail, before the legend -->",
]


def fixture_c(tmp_path):
    return build(tmp_path, legacy_index(C_LINES, tail="<!-- C8: after the legend -->\n"), C_PLANS)


def fixture_d(tmp_path):
    config, plans_dir, index = build(tmp_path, None, A_PLANS)
    assert gen.write_plans_index(config).exit_code == 0
    return config, plans_dir, index


def fixture_e(tmp_path):
    body = b"# Our plans\r\n\r\nWe track plans in a spreadsheet now.\r\n"
    return build(tmp_path, body, {"Alpha/ALP-Master-Plan.md": A_PLANS["Alpha/ALP-Master-Plan.md"]})


def snapshot(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def args(*flags):
    return mig.build_parser().parse_args(list(flags))


def write_args(*extra):
    return args("--write", "--allow-untracked-tree", *extra)


def plan_of(config, index):
    return mig.plan_migration(config, index, read_text(index), migration_date=DATE)


def rel(plan_dir, path):
    return None if path is None else Path(path).relative_to(plan_dir).as_posix()


def section(text, heading):
    match = re.search(rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", text, re.DOTALL | re.MULTILINE)
    return match.group(1) if match else None


def ledger_of(plans_dir):
    return (plans_dir / mig.LEDGER_FILENAME).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. Shape
# ---------------------------------------------------------------------------


def test_the_seed_constant_is_the_shipped_seed_blob():
    assert hashlib.sha256(SEED_LF.encode("utf-8")).hexdigest().startswith("0106791202")


def test_shape_legacy_generated_unrecognized_and_blank(tmp_path):
    _c, _p, index_a = fixture_a(tmp_path / "a")
    _c, _p, index_d = fixture_d(tmp_path / "d")
    _c, _p, index_e = fixture_e(tmp_path / "e")
    assert mig.classify_shape(read_text(index_a))[0] == "legacy"
    assert mig.classify_shape(read_text(index_d))[0] == "generated"
    shape, detail = mig.classify_shape(read_text(index_e))
    assert shape == "unrecognized" and "--report" not in detail
    assert mig.classify_shape("")[0] == "absent" and mig.classify_shape(" \r\n\r\n")[0] == "absent"


def test_a_missing_index_is_refused_and_writes_nothing(tmp_path, capsys):
    config, _plans, index = build(tmp_path, None, A_PLANS)
    before = snapshot(tmp_path)
    assert mig.run(config, write_args()) == 2
    assert "index not found" in capsys.readouterr().err
    assert snapshot(tmp_path) == before and not index.exists()


def test_a_generated_index_is_never_planned(tmp_path, capsys, monkeypatch):
    config, plans_dir, _index = fixture_d(tmp_path)
    monkeypatch.setattr(mig, "plan_migration", lambda *a, **k: pytest.fail("a generated index was planned"))
    before = snapshot(tmp_path)
    assert mig.run(config, write_args()) == 0
    assert "CLEAN" in capsys.readouterr().out
    assert snapshot(tmp_path) == before
    assert not (plans_dir / mig.LEDGER_FILENAME).exists()
    assert not (tmp_path / "proj" / "planwise" / "upgrade-backups").exists()


def test_an_unrecognized_index_is_refused_naming_report(tmp_path, capsys):
    config, _plans, _index = fixture_e(tmp_path)
    before = snapshot(tmp_path)
    assert mig.run(config, write_args()) == 2
    assert "unrecognised index shape" in capsys.readouterr().err
    assert snapshot(tmp_path) == before


# ---------------------------------------------------------------------------
# 2. Positional attribution
# ---------------------------------------------------------------------------


def test_positional_attribution_on_fixture_a(tmp_path):
    config, plans_dir, index = fixture_a(tmp_path)
    plan = plan_of(config, index)
    got = [(i.line, i.kind, rel(plans_dir, i.dest), i.nbytes, i.reason) for i in plan["items"]]
    assert got == [
        (7, mig.KIND_COMMENT, "Beta/BET-Master-Plan.md", 58, None),
        (8, mig.KIND_NARRATIVE, "Gamma/GAM-Master-Plan.md", 21, None),
    ]
    assert plan["items"][1].text == "Sprint 2 of 3 running"


def test_three_consecutive_comments_all_follow_the_row_before_them(tmp_path):
    config, plans_dir, index = fixture_c(tmp_path)
    plan = plan_of(config, index)
    by_line = {i.line: rel(plans_dir, i.dest) for i in plan["items"]}
    assert by_line[7] == by_line[8] == by_line[9] == "One/ONE-Master-Plan.md"


def test_a_comment_naming_another_plan_still_lands_on_its_preceding_row(tmp_path):
    lines = [ALP, "<!-- BET: this note plainly describes Beta, not Alpha -->", BET]
    config, plans_dir, index = build(tmp_path, legacy_index(lines), A_PLANS)
    [item] = plan_of(config, index)["items"]
    assert rel(plans_dir, item.dest) == "Alpha/ALP-Master-Plan.md"


def test_no_content_heuristic_exists_in_the_migrator_sources():
    banned = re.compile(r"difflib|SequenceMatcher|shingle|jaccard|similarity|fuzzy|levenshtein", re.IGNORECASE)
    for name in ("migrate_plans_index.py", "migrate_plans_scan.py", "plans_migration.py"):
        assert not banned.search((SCRIPTS / name).read_text(encoding="utf-8")), name


# ---------------------------------------------------------------------------
# 3. Resolution
# ---------------------------------------------------------------------------


def test_prefix_strip_and_root_path_resolution_on_fixture_b(tmp_path):
    config, plans_dir, index = fixture_b(tmp_path)
    plan = plan_of(config, index)
    got = [(i.line, rel(plans_dir, i.dest)) for i in plan["items"]]
    assert got == [
        (6, "Alpha/Exec-ALP/ALP-Master-Plan.md"),
        (8, "Beta/Meta-BET/BET-META-Master-Plan.md"),
        (10, "Gamma/GAM-Master-Plan.md"),
    ]
    assert plan["prefixed_rows"] == 3 and plan["root_path_rows"] == 2


def test_a_flat_plan_with_a_root_master_plan_resolves_to_it_not_a_child(tmp_path):
    plans = {
        "Delta/DEL-Master-Plan.md": master_plan("Delta", "IN_PROGRESS", "2026-04-01", "2026-04-02"),
        "Delta/Exec-DEL/DEL-Master-Plan.md": master_plan("Delta", "IN_PROGRESS", "2026-04-03", "2026-04-04"),
    }
    lines = ["| DEL | Delta | IN_PROGRESS | 2026-04-01 | 2026-04-02 | Delta/ |", "<!-- DEL: note -->"]
    config, plans_dir, index = build(tmp_path, legacy_index(lines), plans)
    [item] = plan_of(config, index)["items"]
    assert rel(plans_dir, item.dest) == "Delta/DEL-Master-Plan.md"


def test_a_root_path_with_two_meta_children_and_no_exec_is_unresolvable(tmp_path):
    plans = {
        "Zed/Meta-ZA/ZA-META-Master-Plan.md": master_plan("Zed", "COMPLETE", "2026-05-01", "2026-05-02"),
        "Zed/Meta-ZB/ZB-META-Master-Plan.md": master_plan("Zed", "COMPLETE", "2026-05-03", "2026-05-04"),
    }
    lines = ["| ZED | Zed | COMPLETE | 2026-05-01 | 2026-05-02 | Zed/ |", "<!-- ZED: ambiguous -->"]
    config, _plans_dir, index = build(tmp_path, legacy_index(lines), plans)
    plan = plan_of(config, index)
    [item] = plan["items"]
    assert item.dest is None and item.reason == "unresolvable-master-plan"
    assert [r["abbrev"] for r in plan["unresolved_rows"]] == ["ZED"]


# ---------------------------------------------------------------------------
# 4. Unattributed notes
# ---------------------------------------------------------------------------


def test_unattributed_items_carry_their_reason_and_land_verbatim_in_the_ledger(tmp_path, capsys):
    config, plans_dir, index = fixture_c(tmp_path)
    plan = plan_of(config, index)
    reasons = {i.line: i.reason for i in plan["items"] if i.dest is None}
    assert reasons == {5: "no-preceding-row", 11: "unresolvable-master-plan", 27: "outside-table-region"}
    assert mig.run(config, write_args()) == 0, capsys.readouterr()
    notes = section(ledger_of(plans_dir), "Unattributed Index Notes")
    for text in ("<!-- C1: before any row -->", "<!-- C5: after a row whose Master Plan is missing -->",
                 "<!-- C8: after the legend -->"):
        assert text in notes
    assert "no-preceding-row" in notes and "outside-table-region" in notes


def test_an_attributable_comment_never_appears_in_the_unattributed_section(tmp_path, capsys):
    config, plans_dir, _index = fixture_c(tmp_path)
    assert mig.run(config, write_args()) == 0, capsys.readouterr()
    notes = section(ledger_of(plans_dir), "Unattributed Index Notes")
    for tag in ("C2:", "C3:", "C4:", "C6:", "C7:"):
        assert tag not in notes
    assert "an appended" not in notes


def test_a_six_cell_line_after_the_legend_is_kept_verbatim_never_a_row(tmp_path, capsys):
    stray = "| XXX | Stray | COMPLETE | 2026-01-01 | 2026-01-02 | Stray/ |"
    config, plans_dir, _index = build(tmp_path, legacy_index([ALP], tail=stray + "\n"), A_PLANS)
    plan = plan_of(config, config["_plans_index"])
    [item] = [i for i in plan["items"] if i.dest is None]
    assert item.reason == "outside-table-region" and item.text == stray
    assert mig.run(config, write_args()) == 0, capsys.readouterr()
    assert stray in section(ledger_of(plans_dir), "Unattributed Index Notes")


def test_a_multi_line_comment_is_one_item_labelled_with_its_first_line(tmp_path):
    config, plans_dir, index = fixture_c(tmp_path)
    plan = plan_of(config, index)
    [item] = [i for i in plan["items"] if i.text.startswith("<!-- C6")]
    assert item.line == 13 and item.nbytes == 41 and item.text.count("\r\n") == 1
    assert rel(plans_dir, item.dest) == "Three/THR-Master-Plan.md"


def test_a_wrapped_token_drops_its_closing_marker_with_it(tmp_path):
    row = "| ALP | Alpha | **COMPLETE** — closed early | 2026-01-10 | 2026-01-20 | Alpha/ |"
    config, _plans_dir, index = build(tmp_path, legacy_index([row]), A_PLANS)
    [item] = plan_of(config, index)["items"]
    assert item.text == "— closed early"


def test_unresolved_rows_are_listed_verbatim_before_the_generator_drops_them(tmp_path, capsys):
    config, plans_dir, _index = fixture_c(tmp_path)
    assert mig.run(config, write_args()) == 0, capsys.readouterr()
    assert TWO in section(ledger_of(plans_dir), "Unresolved Rows")


# ---------------------------------------------------------------------------
# 5. Master Plan wins
# ---------------------------------------------------------------------------


def test_a_differing_row_token_is_one_status_changed_entry(tmp_path):
    config, _plans_dir, index = fixture_a(tmp_path)
    changes = plan_of(config, index)["status_changes"]
    assert [(c["abbrev"], c["before"], c["after"], c["line"]) for c in changes] == [("GAM", "IN_PROGRESS", "COMPLETE", 8)]


def test_an_emoji_only_row_cell_is_a_status_change_and_the_agreeing_rows_are_not(tmp_path):
    config, _plans_dir, index = fixture_b(tmp_path)
    changes = plan_of(config, index)["status_changes"]
    assert [(c["abbrev"], c["raw"], c["after"]) for c in changes] == [("GAM", "**✅**", "COMPLETE")]


def test_no_master_plan_status_line_changes(tmp_path, capsys):
    config, plans_dir, _index = fixture_a(tmp_path)
    before = {k: re.findall(rb"(?m)^\*\*Status:\*\*[^\r\n]*", v) for k, v in snapshot(plans_dir).items() if "Master" in k}
    assert mig.run(config, write_args()) == 0, capsys.readouterr()
    after = {k: re.findall(rb"(?m)^\*\*Status:\*\*[^\r\n]*", v) for k, v in snapshot(plans_dir).items() if "Master" in k}
    assert before == after
    assert "| GAM | IN_PROGRESS | COMPLETE |" in section(ledger_of(plans_dir), "Status Changes")


# ---------------------------------------------------------------------------
# 6. Rows are counted before they are keyed
# ---------------------------------------------------------------------------


def test_a_repeated_path_loses_no_note_and_is_ledgered(tmp_path, capsys):
    lines = [ALP, "<!-- first note -->", ALP, "<!-- second note -->"]
    config, plans_dir, index = build(tmp_path, legacy_index(lines), A_PLANS)
    plan = plan_of(config, index)
    assert [rel(plans_dir, i.dest) for i in plan["items"]] == ["Alpha/ALP-Master-Plan.md"] * 2
    assert [(d["path"], d["lines"]) for d in plan["duplicates"]] == [("Alpha/", [5, 7])]
    assert mig.run(config, write_args()) == 0, capsys.readouterr()
    body = (plans_dir / "Alpha" / "ALP-Master-Plan.md").read_bytes()
    assert b"<!-- first note -->" in body and b"<!-- second note -->" in body
    assert "- Duplicate Paths: 1" in ledger_of(plans_dir)


def test_a_unique_path_fixture_ledgers_no_duplicate(tmp_path, capsys):
    config, plans_dir, _index = fixture_a(tmp_path)
    assert mig.run(config, write_args()) == 0, capsys.readouterr()
    assert "- Duplicate Paths: 0" in ledger_of(plans_dir)


# ---------------------------------------------------------------------------
# 8. The append
# ---------------------------------------------------------------------------


def test_the_appended_block_layout_is_byte_exact_and_a_prefix_extension(tmp_path, capsys):
    config, plans_dir, _index = fixture_a(tmp_path)
    assert mig.run(config, write_args()) == 0, capsys.readouterr()
    head = f"\n## Index Notes (harvested {DATE})\n\n{BANNER.format(date=DATE)}\n"
    bet = head + "\n*From 00-Index-Plans.md line 7 (HTML comment).*\n" + A_COMMENT + "\n"
    gam = ("\n" + head + "\n*From 00-Index-Plans.md line 8 (Status cell text after the leading token).*\n"
           "Sprint 2 of 3 running\n")
    for key, block in (("Beta/BET-Master-Plan.md", bet), ("Gamma/GAM-Master-Plan.md", gam)):
        pre, post = A_PLANS[key], (plans_dir / key).read_bytes()
        assert post.startswith(pre) and post[len(pre):] == block.encode("utf-8")
    assert len(BANNER.format(date=DATE).encode("utf-8")) == 213
    assert (plans_dir / "Alpha/ALP-Master-Plan.md").read_bytes() == A_PLANS["Alpha/ALP-Master-Plan.md"]


def test_the_append_uses_the_master_plans_own_line_ending(tmp_path, capsys):
    lines = [ALP, "<!-- ALP: a note -->", BET]
    config, plans_dir, _index = build(tmp_path, legacy_index(lines, nl="\n"), A_PLANS)
    assert mig.run(config, write_args()) == 0, capsys.readouterr()
    pre = A_PLANS["Alpha/ALP-Master-Plan.md"]
    post = (plans_dir / "Alpha/ALP-Master-Plan.md").read_bytes()
    added = post[len(pre):]
    assert post.startswith(pre) and added.count(b"\n") == added.count(b"\r\n") > 0


def test_an_item_already_present_is_skipped_and_ledgered(tmp_path, capsys):
    old = f"\n## Index Notes (harvested 2026-09-01)\n\n{BANNER.format(date='2026-09-01')}\n"
    old += "\n*From 00-Index-Plans.md line 7 (HTML comment).*\n" + A_COMMENT + "\n"
    plans = dict(A_PLANS)
    plans["Beta/BET-Master-Plan.md"] = A_PLANS["Beta/BET-Master-Plan.md"] + old.encode("utf-8")
    config, plans_dir, index = build(tmp_path, legacy_index([ALP, BET, A_COMMENT, GAM]), plans)
    plan = plan_of(config, index)
    assert [rel(plans_dir, a["path"]) for a in plan["appends"]] == ["Gamma/GAM-Master-Plan.md"]
    assert mig.run(config, write_args()) == 0, capsys.readouterr()
    assert (plans_dir / "Beta/BET-Master-Plan.md").read_bytes() == plans["Beta/BET-Master-Plan.md"]
    assert "already-present" in section(ledger_of(plans_dir), "Appended Index Notes")


def test_a_short_item_matching_by_chance_is_not_already_present(tmp_path):
    plans = dict(A_PLANS)
    plans["Gamma/GAM-Master-Plan.md"] = A_PLANS["Gamma/GAM-Master-Plan.md"] + b"\nSprint 2 of 3 running\n"
    config, plans_dir, index = build(tmp_path, legacy_index([ALP, BET, A_COMMENT, GAM]), plans)
    plan = plan_of(config, index)
    assert "Gamma/GAM-Master-Plan.md" in [rel(plans_dir, a["path"]) for a in plan["appends"]]


# ---------------------------------------------------------------------------
# 9. The generator runs after the appends
# ---------------------------------------------------------------------------


def test_after_the_write_the_generator_check_exits_zero_and_a_second_run_is_clean(tmp_path, capsys):
    config, _plans_dir, index = fixture_a(tmp_path)
    assert mig.run(config, write_args()) == 0, capsys.readouterr()
    result = gen.check_plans_index(config)
    assert result.exit_code == 0 and result.compared == 3
    data = index.read_bytes()
    assert len(data) == 1123 and data.count(b"\n") == data.count(b"\r\n")
    assert [r.abbrev for r in result.render.rows] == ["ALP", "BET", "GAM"]
    assert re.search(rb"\| GAM \| Gamma \| COMPLETE \| 2026-03-01 \| 2026-03-05 \|", data)
    before = snapshot(tmp_path)
    assert mig.run(config, write_args()) == 0
    assert "CLEAN" in capsys.readouterr().out
    assert snapshot(tmp_path) == before


def test_the_migrator_is_the_only_plans_caller_of_replace_legacy_true():
    hits = []
    for path in sorted(SCRIPTS.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        if re.search(r"write_plans_index\([^)]*replace_legacy=True", text, re.DOTALL):
            hits.append(path.name)
    assert hits == ["migrate_plans_index.py"]


def test_a_bare_seed_migrates_to_the_generators_render_and_names_the_seed(tmp_path, capsys):
    crlf = SEED_LF.replace("\n", "\r\n").encode("utf-8")
    config, plans_dir, index = build(tmp_path, crlf, {})
    assert hashlib.sha256(crlf).hexdigest().startswith("6922b74f")
    assert mig.run(config, write_args()) == 0, capsys.readouterr()
    assert len(index.read_bytes()) == 933
    ledger = ledger_of(plans_dir)
    assert "legacy seed" in ledger and "6922b74f" in ledger and "- Appended items: 0" in ledger
    assert gen.check_plans_index(config).exit_code == 0


def test_a_bare_lf_seed_gives_the_same_states(tmp_path, capsys):
    config, plans_dir, index = build(tmp_path, SEED_LF.encode("utf-8"), {})
    assert mig.run(config, write_args()) == 0, capsys.readouterr()
    assert len(index.read_bytes()) == 910 and "0106791202" in ledger_of(plans_dir)


# ---------------------------------------------------------------------------
# 10. Plan-time refusals
# ---------------------------------------------------------------------------


def test_without_a_git_safety_net_the_run_is_refused_naming_the_flag(tmp_path, capsys):
    config, _plans_dir, _index = fixture_a(tmp_path)
    before = snapshot(tmp_path)
    assert mig.run(config, args("--write")) == 2
    assert "--allow-untracked-tree" in capsys.readouterr().err
    assert snapshot(tmp_path) == before


def test_the_same_fixture_with_allow_untracked_tree_migrates(tmp_path, capsys):
    config, _plans_dir, _index = fixture_a(tmp_path)
    assert mig.run(config, write_args()) == 0, capsys.readouterr()


def _git(root, *argv):
    subprocess.run(["git", "-C", str(root), *argv], check=True, capture_output=True)


def _committed(tmp_path):
    config, plans_dir, index = fixture_a(tmp_path)
    root = tmp_path / "proj"
    for argv in (["init", "-q"], ["config", "user.email", "t@example.com"], ["config", "user.name", "t"],
                 ["add", "-A"], ["commit", "-q", "-m", "fixture"]):
        _git(root, *argv)
    return config, plans_dir, index


def test_a_dirty_master_plan_in_the_append_set_is_refused_naming_force(tmp_path, capsys):
    config, plans_dir, _index = _committed(tmp_path)
    bet = plans_dir / "Beta/BET-Master-Plan.md"
    bet.write_bytes(bet.read_bytes() + b"\nuncommitted edit\n")
    before = snapshot(tmp_path / "proj" / "planwise")
    assert mig.run(config, args("--write")) == 2
    assert "--force" in capsys.readouterr().err
    assert snapshot(tmp_path / "proj" / "planwise") == before


def test_a_dirty_master_plan_outside_the_append_set_does_not_refuse(tmp_path, capsys):
    config, plans_dir, _index = _committed(tmp_path)
    alp = plans_dir / "Alpha/ALP-Master-Plan.md"
    alp.write_bytes(alp.read_bytes() + b"\nuncommitted edit\n")
    assert mig.run(config, args("--write")) == 0, capsys.readouterr()


def test_force_lets_a_dirty_append_set_migrate(tmp_path, capsys):
    config, plans_dir, _index = _committed(tmp_path)
    bet = plans_dir / "Beta/BET-Master-Plan.md"
    bet.write_bytes(bet.read_bytes() + b"\nuncommitted edit\n")
    assert mig.run(config, args("--write", "--force")) == 0, capsys.readouterr()


def test_an_over_budget_render_is_refused_before_any_write(tmp_path, capsys, monkeypatch):
    config, _plans_dir, _index = fixture_a(tmp_path)
    monkeypatch.setattr(gen, "HUB_TOKEN_BUDGET", 10)
    before = snapshot(tmp_path)
    assert mig.run(config, write_args()) == 2
    err = capsys.readouterr().err
    assert "budget" in err and "tokens" in err
    assert snapshot(tmp_path) == before


# ---------------------------------------------------------------------------
# 11. Resume
# ---------------------------------------------------------------------------


def test_a_rerun_after_an_interruption_appends_nothing_twice_and_reuses_the_date(tmp_path, capsys, monkeypatch):
    config, plans_dir, _index = fixture_a(tmp_path)

    def crash(*_a, **_k):
        raise RuntimeError("simulated crash between the appends and the generator write")

    with monkeypatch.context() as patched:
        patched.setattr(gen, "write_plans_index", crash)
        assert mig.run(config, write_args()) == 1
    capsys.readouterr()
    appended = {k: (plans_dir / k).read_bytes() for k in ("Beta/BET-Master-Plan.md", "Gamma/GAM-Master-Plan.md")}
    assert appended["Beta/BET-Master-Plan.md"] != A_PLANS["Beta/BET-Master-Plan.md"]
    monkeypatch.setattr(mig, "_today", lambda: "2026-10-05")
    assert mig.run(config, write_args()) == 0, capsys.readouterr()
    for key, data in appended.items():
        assert (plans_dir / key).read_bytes() == data
        assert b"2026-10-05" not in data and DATE.encode() in data
    assert "- Migration date: 2026-10-01" in ledger_of(plans_dir)
    assert gen.check_plans_index(config).exit_code == 0


def test_a_clean_second_run_leaves_the_tree_identical(tmp_path, capsys):
    config, _plans_dir, _index = fixture_a(tmp_path)
    assert mig.run(config, write_args()) == 0
    before = snapshot(tmp_path)
    assert mig.run(config, write_args()) == 0
    assert snapshot(tmp_path) == before


# ---------------------------------------------------------------------------
# 12. --dry-run and --report write nothing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("make", [fixture_a, fixture_b, fixture_c, fixture_d, fixture_e])
@pytest.mark.parametrize("flags", [("--dry-run",), ("--report",), ("--report", "--json")])
def test_dry_run_and_report_write_nothing(tmp_path, capsys, make, flags):
    config, _plans_dir, _index = make(tmp_path)
    before = snapshot(tmp_path)
    code = mig.run(config, args(*flags, "--allow-untracked-tree"))
    capsys.readouterr()
    assert snapshot(tmp_path) == before
    if "--report" in flags:
        assert code == 0


def test_report_json_is_one_object_with_the_documented_fields(tmp_path, capsys):
    config, _plans_dir, _index = fixture_a(tmp_path)
    assert mig.run(config, args("--report", "--json")) == 0
    report = json.loads(capsys.readouterr().out)
    assert list(report) == ["shape", "detail", "index", "rows", "comments", "narrative_cells", "attributable",
                            "unattributed", "uncarried_lines", "root_path_rows", "prefixed_rows", "status_changes",
                            "append_targets", "ready", "would_refuse", "questions"]
    assert report["uncarried_lines"] == 0
    assert (report["shape"], report["rows"], report["comments"], report["narrative_cells"]) == ("legacy", 3, 1, 1)
    assert (report["attributable"], report["unattributed"], report["status_changes"]) == (2, 0, 1)
    assert report["append_targets"] == ["Beta/BET-Master-Plan.md", "Gamma/GAM-Master-Plan.md"]
    assert report["ready"] is True and report["would_refuse"] == []


def test_report_shapes_for_the_other_fixtures(tmp_path, capsys):
    shapes = {}
    for name, make in (("b", fixture_b), ("c", fixture_c), ("d", fixture_d), ("e", fixture_e)):
        config, _plans_dir, _index = make(tmp_path / name)
        assert mig.run(config, args("--report", "--json")) == 0
        shapes[name] = json.loads(capsys.readouterr().out)
    assert shapes["b"]["prefixed_rows"] == 3 and shapes["b"]["root_path_rows"] == 2
    assert shapes["c"]["unattributed"] == 3
    assert shapes["d"]["shape"] == "generated" and shapes["d"]["ready"] is False
    assert shapes["e"]["shape"] == "unrecognized" and shapes["e"]["ready"] is False


def test_a_dry_run_on_a_dirty_tree_prints_the_plan_and_names_the_gate(tmp_path, capsys):
    config, plans_dir, _index = _committed(tmp_path)
    bet = plans_dir / "Beta/BET-Master-Plan.md"
    bet.write_bytes(bet.read_bytes() + b"\nuncommitted edit\n")
    before = snapshot(tmp_path / "proj" / "planwise")
    assert mig.run(config, args()) == 1
    out = capsys.readouterr().out
    assert "Plans index migration plan" in out and "DRY-RUN" in out
    assert "would refuse" in out and "--force" in out
    assert snapshot(tmp_path / "proj" / "planwise") == before
    assert mig.run(config, args("--write")) == 2
    assert snapshot(tmp_path / "proj" / "planwise") == before


def test_a_json_dry_run_outside_git_names_the_gate_in_would_refuse(tmp_path, capsys):
    config, _plans_dir, _index = fixture_a(tmp_path)
    assert mig.run(config, args("--json")) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["ready"] is False
    assert any("--allow-untracked-tree" in reason for reason in report["would_refuse"])


# ---------------------------------------------------------------------------
# 13. Review regressions
# ---------------------------------------------------------------------------


def test_a_crlf_multi_line_note_in_an_lf_master_plan_is_recognised_on_resume(tmp_path, capsys, monkeypatch):
    lines = [BET, "<!-- BET: a note that", "spans two lines -->"]
    config, plans_dir, _index = build(tmp_path, legacy_index(lines), A_PLANS)

    def crash(*_a, **_k):
        raise RuntimeError("simulated crash between the appends and the generator write")

    with monkeypatch.context() as patched:
        patched.setattr(gen, "write_plans_index", crash)
        assert mig.run(config, write_args()) == 1
    capsys.readouterr()
    first = (plans_dir / "Beta/BET-Master-Plan.md").read_bytes()
    assert b"\r\n" in first and first.count(b"## Index Notes") == 1
    assert mig.run(config, write_args()) == 0, capsys.readouterr()
    body = (plans_dir / "Beta/BET-Master-Plan.md").read_bytes()
    assert body == first
    assert "- Already-present items: 1" in ledger_of(plans_dir)


def test_an_unclosed_comment_is_refused_naming_its_line_before_any_write(tmp_path, capsys):
    lines = [ALP, "<!-- ALP: a note that never closes", BET]
    config, _plans_dir, _index = build(tmp_path, legacy_index(lines), A_PLANS)
    before = snapshot(tmp_path)
    assert mig.run(config, write_args()) == 2
    err = capsys.readouterr().err
    assert "line 6" in err and "close the comment" in err
    assert snapshot(tmp_path) == before


ARCHIVED = "## Archived\n\nOld plans we dropped:\n\n- Zeta was cancelled in March.\n"


def test_prose_outside_the_table_is_listed_verbatim_and_the_bytes_balance(tmp_path, capsys):
    config, plans_dir, index = build(tmp_path, legacy_index([ALP], tail=ARCHIVED), A_PLANS)
    plan = plan_of(config, index)
    listed = ["## Archived", "Old plans we dropped:", "- Zeta was cancelled in March."]
    assert [text for _line, text in plan["uncarried"]] == listed
    acc = mig.accounting(plan)
    assert acc["index"] == len(index.read_bytes()) and acc["unaccounted"] == 0
    assert acc["uncarried"] == sum(len(t.encode("utf-8")) for t in listed)
    assert mig.run(config, write_args()) == 0, capsys.readouterr()
    ledger = ledger_of(plans_dir)
    # A listed line may itself start with `## `, so bound the section by the ledger's next heading.
    uncarried = ledger.split("\n## Uncarried Index Lines\n", 1)[1].split("\n## Unresolved Rows\n", 1)[0]
    for text in listed:
        assert f"```\n{text}\n```" in uncarried
    assert "- Uncarried index lines: 3" in ledger and "- Unaccounted: 0" in ledger


def test_byte_accounting_detects_a_dropped_item(tmp_path):
    config, _plans_dir, index = fixture_c(tmp_path)
    plan = plan_of(config, index)
    assert mig.accounting(plan)["unaccounted"] == 0
    dropped = plan["items"].pop(0)
    assert mig.accounting(plan)["unaccounted"] == dropped.nbytes


@pytest.mark.parametrize("nl", ["\n", "\r\n"])
def test_the_seed_scaffold_yields_no_listed_line_and_no_item(tmp_path, nl):
    config, _plans_dir, index = build(tmp_path, SEED_LF.replace("\n", nl).encode("utf-8"), {})
    plan = plan_of(config, index)
    assert plan["items"] == [] and plan["uncarried"] == []
    assert mig.accounting(plan)["unaccounted"] == 0
    _c, _p, index_a = fixture_a(tmp_path / "a")
    assert plan_of(_c, index_a)["uncarried"] == []


def _failed_verdict(tmp_path, capsys, monkeypatch):
    """A migration whose generator wrote the index but whose check failed: the ledger reads `failed`."""
    config, plans_dir, index = fixture_a(tmp_path)
    real = mig._run_generator_steps

    def failing_check(cfg):
        return {**real(cfg), "check_exit": 2, "check_findings": ["simulated-drift"]}

    with monkeypatch.context() as patched:
        patched.setattr(mig, "_run_generator_steps", failing_check)
        assert mig.run(config, write_args()) == 1
    capsys.readouterr()
    assert "- Generator verdict: failed" in ledger_of(plans_dir)
    assert mig.classify_shape(read_text(index))[0] == "generated"
    return config, plans_dir


def test_a_resumed_generator_step_rewrites_the_ledger_verdict(tmp_path, capsys, monkeypatch):
    config, plans_dir = _failed_verdict(tmp_path, capsys, monkeypatch)
    monkeypatch.setattr(mig, "_today", lambda: "2026-10-07")
    assert mig.run(config, write_args()) == 0, capsys.readouterr()
    ledger = ledger_of(plans_dir)
    assert "- Generator verdict: clean" in ledger and "- Migration date: 2026-10-01" in ledger
    capsys.readouterr()
    assert mig.run(config, args()) == 0
    assert "CLEAN" in capsys.readouterr().out


def test_a_raising_generator_on_resume_is_a_clean_failure(tmp_path, capsys, monkeypatch):
    config, _plans_dir = _failed_verdict(tmp_path, capsys, monkeypatch)

    def crash(*_a, **_k):
        raise RuntimeError("generator crashed on resume")

    monkeypatch.setattr(gen, "write_plans_index", crash)
    assert mig.run(config, write_args()) == 1
    err = capsys.readouterr().err
    assert "FAIL" in err and "generator crashed on resume" in err and "Traceback" not in err


def test_a_nested_planwise_root_logs_dispositions_beside_its_backups(tmp_path, capsys):
    config, _plans_dir, _index = fixture_a(tmp_path)
    config["_project_root"] = tmp_path  # the planwise root sits two levels down, at proj/planwise
    assert mig.run(config, write_args()) == 0, capsys.readouterr()
    pair = config["_planwise_root"] / "upgrade-backups" / f"{mig.CLI_PAIR}-to-{DATE}"
    log = (pair / "DISPOSITIONS.md").read_text(encoding="utf-8")
    assert len([ln for ln in log.splitlines() if "plans-backed-up:" in ln]) == 3
    assert (pair / "plans" / "00-Index-Plans.md").is_file()


def test_two_rows_differing_only_in_case_make_one_append_group(tmp_path, capsys, monkeypatch):
    upper = "| ALP | Alpha | COMPLETE | 2026-01-10 | 2026-01-20 | Alpha/ |"
    lower = "| ALP | Alpha | COMPLETE | 2026-01-10 | 2026-01-20 | alpha/ |"
    lines = [upper, "<!-- first -->", lower, "<!-- second -->"]
    config, plans_dir, index = build(tmp_path, legacy_index(lines), A_PLANS)
    real = mig._resolve

    def case_insensitive(plans, entries, path, abbrev):
        """Stands in for a case-insensitive file system whose path objects compare case-sensitively: the
        lower-case row resolves to the same Master Plan under a second spelling."""
        if path != "alpha/":
            return real(plans, entries, path, abbrev)
        file, child = real(plans, entries, "Alpha/", abbrev)
        return file.parent / ".." / file.parent.name / file.name, child

    monkeypatch.setattr(mig, "_resolve", case_insensitive)
    plan = plan_of(config, index)
    [append] = plan["appends"]
    assert [i.text for i in append["items"]] == ["<!-- first -->", "<!-- second -->"]
    assert mig.run(config, write_args()) == 0, capsys.readouterr()
    body = (plans_dir / "Alpha/ALP-Master-Plan.md").read_bytes()
    assert body.count(b"## Index Notes") == 1 and b"<!-- first -->" in body and b"<!-- second -->" in body


def test_report_is_mutually_exclusive_with_write():
    with pytest.raises(SystemExit):
        args("--report", "--write")


def test_the_cli_carries_every_documented_flag():
    parsed = args("--dry-run", "--json", "--force", "--allow-untracked-tree", "--config", "x.yaml")
    assert parsed.dry_run and parsed.json and parsed.force and parsed.allow_untracked_tree
    assert parsed.write is False and parsed.report is False
