"""Tests for migrate_backlog_items.py: the upgrade step that repairs the shape of backlog item files.

Every fixture is built in tmp_path as bytes, never under plugins/planwise/. The index is a generated
one (written by the real generator), because the step stays silent on a hand-authored index. The legacy
section is copied from a real item, per the fixture-from-real-producer rule.

The known-bad arm of the preservation case is in the file: the same corrupt write, with the diff
switched off, is kept on disk, so the refusal test discriminates.
"""
import contextlib
import io
import re
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ itself, for the sibling import below

import artifact_upgrade
import backlog_migration as bm
import backlog_questions as bq
import config_loader
import generate_backlog_index as gen
import migrate_backlog_items as mbi
from backlog_item_shape import GAP_CLASSES, scan_item_shapes
from config_gen import InitConfig
from test_backlog_migration_wiring import TARGET_VERSION, _legacy_project

INDEX = "00-Index-Backlog.md"
CONFIG = ('project:\n  name: "fixture"\n  backlog_dir: "Backlog"\n  index_files:\n'
          f'    backlog: "{INDEX}"\nabbreviations:\n  INFRA: Infrastructure and DevOps\n')
HUB = ("Generated: 2024-01-01\n\n| ID | Title | Priority | Status | Domain | Created | Blocks | Score | File |\n"
       "|---|---|---|---|---|---|---|---|---|\n")
LEGACY_INDEX = ("## Backlog Items\n\n| ID | Feature | Priority | Status | Abbrev | Files |\n|---|---|---|---|---|---|\n"
                "| 001 | A fixture item | Medium | NOT_STARTED | INFRA | [001](BB-001-01-INFRA-Fixture.md) |\n\n"
                "---\n\n*Last Updated: 2024-01-01 — did something.*\n")
# The dated shape of the retired loop-skip section, copied from a real item.
LEGACY_SECTION = (
    "## Loop Decision Needed\n"
    "\n"
    "<!-- loop-decision run=20261012-222015 -->\n"
    "> [!gate] User input needed\n"
    "> Loop run 20261012-222015, 2026-10-12. The loop skipped this item without working it. "
    "Answer the question below, then triage it again.\n"
    "\n"
    "Item 555 asks for three things from a feedback issue. The filing note says the repository "
    "claims were not re-verified, and the loop's premise probe found two of them do not hold as "
    "written. Route is B, score 25, matching route_at_init, with no route_hint. Choose: (A) confirm "
    "the item as written; (B) split it so the reference passage lands first; or (C) name a "
    "different approach.\n"
)
KEEP = "Unique sentence that must survive the repair."


def item_text(number, *, title="A fixture item", extra_fm=(), extra_body="", priority_line: str | None = "**Priority:** Medium",
              domain_line: str | None = "**Domain:** INFRA", footer: str | None = "*Created: 2026-11-18*", eol="\n",
              status="NOT_STARTED"):
    lines = ["---", f"id: {number:03d}", f'title: "{title}"', "priority: Medium", f"status: {status}", "abbrev: INFRA",
             "created: 2026-11-18", "blocks: []", *extra_fm, "---", "", f"# BB-{number:03d}-01-INFRA-Fixture: {title}", ""]
    lines += [line for line in (priority_line, domain_line) if line is not None]
    lines += ["", "---", ""]
    for heading in ("Summary", "Problem", "Proposed Solution", "Acceptance Criteria"):
        lines += [f"## {heading}", "", "Text.", ""]
    if extra_body:
        lines += [extra_body, ""]
    lines += ["## Related", "", "- none", "", "---", ""]
    if footer is not None:
        lines.append(footer)
    return ("\n".join(lines) + "\n").replace("\n", eol).encode("utf-8")


def _project(tmp_path, items: dict, index: str = HUB):
    """A project with the given item files (number -> bytes) and a generated index over them."""
    root = tmp_path / "proj"
    backlog = root / "planwise" / "Backlog"
    (backlog / "Archive").mkdir(parents=True)
    (root / "planwise" / "config.yaml").write_bytes(CONFIG.encode("utf-8"))
    (backlog / INDEX).write_bytes(index.encode("utf-8"))
    (backlog / "00-Changelog-Backlog.md").write_bytes(f"[← {INDEX}]({INDEX})\n".encode())
    for number, data in items.items():
        (backlog / f"BB-{number:03d}-01-INFRA-Fixture.md").write_bytes(data)
    cfg = InitConfig(project_name="fixture", project_root=root, plugin_root=SCRIPTS.parent)
    if index == HUB:
        config = config_loader.load_config(Path(__file__), config_path=root / "planwise" / "config.yaml")
        naming = gen._index_naming(config["_index_path"])
        with contextlib.redirect_stdout(io.StringIO()):
            written = gen._cmd_write(config["_backlog_dir"], config["_archive_dir"], config["_index_path"], naming,
                                     config, json_out=False)
        assert written == 0
    return cfg, backlog


def _snapshot(folder: Path) -> dict:
    return {p.relative_to(folder).as_posix(): p.read_bytes() for p in folder.rglob("*") if p.is_file()}


def _run(cfg, answers=None):
    return mbi.migrate_backlog_items(cfg, "1.0", "1.1", answers)


def _item_path(backlog: Path, number: int) -> Path:
    return backlog / f"BB-{number:03d}-01-INFRA-Fixture.md"


def _mechanical_left(backlog: Path) -> dict:
    classes = scan_item_shapes(backlog).classes
    return {key: ids for key, ids in classes.items() if ids and key in mbi.MECHANICAL}


def test_a_clean_project_writes_nothing_and_prints_nothing(tmp_path, capsys):
    cfg, backlog = _project(tmp_path, {1: item_text(1)})
    before = _snapshot(backlog.parent)
    report = _run(cfg)
    mbi._emit_backlog_items_banner(report)
    assert report.state == "clean" and report.backed_up == [] and report.remaining == {}
    assert _snapshot(backlog.parent) == before
    assert capsys.readouterr().out == ""


def test_every_mechanical_class_is_repaired(tmp_path):
    drifted = item_text(1, priority_line=None, domain_line=None, footer=None, extra_body=KEEP,
                        extra_fm=("blocked_by: [900]", "owner: someone"))
    cfg, backlog = _project(tmp_path, {1: drifted, 2: item_text(2, extra_body=LEGACY_SECTION), 3: item_text(3)})
    control = _item_path(backlog, 3).read_bytes()
    assert set(_mechanical_left(backlog)) == set(mbi.MECHANICAL)
    report = _run(cfg)
    assert report.state == "migrated", report.detail
    assert (report.generator_write_exit, report.generator_check_exit) == (0, 0)
    assert _mechanical_left(backlog) == {}
    one = _item_path(backlog, 1).read_text(encoding="utf-8")
    assert re.search(r"^# BB-001-01.*\n\n\*\*Priority:\*\* Medium\n\*\*Domain:\*\* INFRA\n\n---", one, re.MULTILINE)
    assert one.rstrip().endswith("---\n\n*Created: 2026-11-18*") and KEEP in one
    assert "blocked_by" not in one.split("\n---\n", 1)[0] and "owner:" not in one.split("\n---\n", 1)[0]
    assert "## Notes\n\n- `blocked_by`: [900]\n- `owner`: someone\n" in one
    assert one.index("## Notes") < one.index("## Related")
    two = _item_path(backlog, 2).read_text(encoding="utf-8")
    assert "## Loop Decision Needed" not in two and "### Q1. Loop decision (run 20261012-222015)" in two
    assert _item_path(backlog, 3).read_bytes() == control
    assert report.counts == {"lines": 2, "footer": 1, "keys": 2, "fold": 1}
    assert [n for n in report.notes if "blocked_by" in n and "blocks:" in n]


def test_the_fold_goes_through_fold_item(tmp_path, monkeypatch):
    calls = []
    real = bq.fold_item
    monkeypatch.setattr(bq, "fold_item", lambda path, dry_run=False: calls.append(path.name) or real(path, dry_run))
    cfg, _backlog = _project(tmp_path, {1: item_text(1, extra_body=LEGACY_SECTION)})
    assert _run(cfg).state == "migrated" and len(calls) == 1


def test_a_fold_that_is_refused_is_reported_and_the_section_stays(tmp_path):
    broken = LEGACY_SECTION + "```\nnever closed\n"
    cfg, backlog = _project(tmp_path, {1: item_text(1, extra_body=broken, priority_line=None)})
    report = _run(cfg)
    assert report.state == "migrated", report.detail
    text = _item_path(backlog, 1).read_text(encoding="utf-8")
    assert "## Loop Decision Needed" in text and "**Priority:** Medium" in text
    assert [n for n in report.notes if "left in place" in n]


def test_each_backup_predates_its_write_and_is_byte_exact(tmp_path, monkeypatch):
    cfg, backlog = _project(tmp_path, {1: item_text(1, footer=None), 2: item_text(2, priority_line=None)})
    before = _snapshot(backlog)
    backups = backlog.parent / "upgrade-backups" / "1.0-to-1.1" / "backlog-items"
    seen, real = [], bm._write_atomic

    def spy(path, data):
        name = path.relative_to(backlog).as_posix()
        seen.append((name, (backups / name).is_file() and (backups / name).read_bytes() == before[name]))
        return real(path, data)

    monkeypatch.setattr(bm, "_write_atomic", spy)
    report = _run(cfg)
    assert report.state == "migrated", report.detail
    items = [entry for entry in seen if entry[0].startswith("BB-")]
    assert len(items) == 2 and all(ok for _name, ok in items), seen
    dispositions = (backlog.parent / "upgrade-backups" / "1.0-to-1.1" / "DISPOSITIONS.md").read_text(encoding="utf-8")
    assert dispositions.count(mbi.ACTION) == 2 and "upgrade-backups/1.0-to-1.1/backlog-items/BB-" in dispositions


def test_a_second_run_is_a_no_op(tmp_path):
    cfg, backlog = _project(tmp_path, {1: item_text(1, footer=None, extra_fm=("owner: someone",))})
    assert _run(cfg).state == "migrated"
    after_first = _snapshot(backlog.parent)
    report = _run(cfg)
    assert report.state == "clean" and report.backed_up == [] and report.written == []
    assert _snapshot(backlog.parent) == after_first


def _drop_the_kept_line_once(monkeypatch):
    """Make the first write of each file lose one body line. A later write, the restore, passes through."""
    dropped, real = set(), bm._write_atomic

    def corrupting(path, data):
        if path.name.startswith("BB-") and path.name not in dropped:
            dropped.add(path.name)
            data = data.replace(KEEP.encode("utf-8") + b"\n", b"")
        return real(path, data)

    monkeypatch.setattr(bm, "_write_atomic", corrupting)


def test_a_preservation_miss_restores_every_file_and_refuses(tmp_path, monkeypatch):
    cfg, backlog = _project(tmp_path, {1: item_text(1, footer=None, extra_body=KEEP), 2: item_text(2, footer=None)})
    before = _snapshot(backlog.parent)
    _drop_the_kept_line_once(monkeypatch)
    report = _run(cfg)
    assert report.state == "refused" and KEEP[:20] in report.detail and "restored" in report.detail
    after = {k: v for k, v in _snapshot(backlog.parent).items() if not k.startswith("upgrade-backups/")}
    assert after == before  # every item file and the index are back to their pre-run bytes
    assert (report.written, report.generator_write_exit) == ([], None)


def test_known_bad_arm_without_the_diff_the_corrupt_write_is_kept(tmp_path, monkeypatch):
    cfg, backlog = _project(tmp_path, {1: item_text(1, footer=None, extra_body=KEEP)})
    _drop_the_kept_line_once(monkeypatch)
    monkeypatch.setattr(mbi, "_dropped", lambda *_args: [])
    assert _run(cfg).state == "migrated"
    assert KEEP not in _item_path(backlog, 1).read_text(encoding="utf-8")


def test_the_banner_prints_the_findings_the_routes_and_the_actions(tmp_path, capsys):
    cfg, _backlog = _project(tmp_path, {1: item_text(1, footer=None, extra_fm=("blocked_by: [900]",)),
                                         2: item_text(2, title="T" * 130)})
    report = _run(cfg)
    mbi._emit_backlog_items_banner(report)
    out = capsys.readouterr().out
    labels = dict(GAP_CLASSES)
    assert "Backlog item shape repair:" in out and "open items scanned: 2" in out
    assert f"~ {labels['footer']}: 1 — 001" in out and f"~ {labels['key-nontemplate']}: 1 — 001" in out
    assert re.search(r"routes before -> after: 001: [ABC] -> [ABC]\b", out)
    assert "generator --check: clean" in out and "backups:  " in out
    assert f"~ {labels['title-over-cap']}: 1 — 002" in out  # a judgment class is left and listed
    assert "action: 001: `blocked_by` now sits under Notes" in out


def test_judgment_classes_are_left_as_written(tmp_path):
    odd = item_text(1, title="T" * 130, extra_body="## An Odd Heading\n\nText.")
    cfg, backlog = _project(tmp_path, {1: odd})
    before = _item_path(backlog, 1).read_bytes()
    report = _run(cfg)
    assert report.state == "clean" and _item_path(backlog, 1).read_bytes() == before
    assert set(report.remaining) == {"title-over-cap", "section-nontemplate"}


def test_a_crlf_item_stays_crlf(tmp_path):
    cfg, backlog = _project(tmp_path, {1: item_text(1, footer=None, extra_fm=("owner: someone",), eol="\r\n")})
    assert _run(cfg).state == "migrated"
    data = _item_path(backlog, 1).read_bytes()
    assert data.count(b"\r\n") == data.count(b"\n") > 0 and b"- `owner`: someone\r\n" in data


def test_a_hand_authored_index_is_left_alone(tmp_path, capsys):
    cfg, backlog = _project(tmp_path, {1: item_text(1, footer=None)}, index=LEGACY_INDEX)
    before = _snapshot(backlog.parent)
    report = _run(cfg)
    mbi._emit_backlog_items_banner(report)
    assert report.state == "skipped" and _snapshot(backlog.parent) == before and capsys.readouterr().out == ""


def test_a_project_without_config_reports_absent(tmp_path):
    cfg = InitConfig(project_name="x", project_root=tmp_path, plugin_root=SCRIPTS.parent)
    assert _run(cfg).state == "absent"


def test_dropped_names_each_missing_line_and_excuses_the_moved_ones():
    assert mbi._dropped("a\nb\nb\n\nc", "a\nb\n", []) == ["b", "c"]
    assert mbi._dropped("a\nowner: x\n", "a\n", ["owner: x"]) == []
    assert mbi._dropped("a\r\nb\r\n", "a\nb\n", []) == []


def test_a_raising_step_never_fails_the_report(tmp_path, monkeypatch):
    cfg, _backlog = _project(tmp_path, {1: item_text(1, footer=None)})
    monkeypatch.setattr(mbi, "_plan_item", lambda *_a: (_ for _ in ()).throw(RuntimeError("boom")))
    report = _run(cfg)
    assert report.state == "error" and "boom" in report.detail


def _archived(backlog: Path, number: int) -> Path:
    return backlog / "Archive" / f"BB-{number:03d}-01-INFRA-Fixture.md"


def _fixture_scores_as_open(cfg, number: int) -> bool:
    """True when the live scorer reads the item as open, the way `/planwise backlog` does."""
    config = config_loader.load_config(Path(__file__), config_path=Path(cfg.project_root) / "planwise" / "config.yaml")
    return mbi._routes(config, [f"{number:03d}"])[f"{number:03d}"] in ("A", "B", "C")


def test_a_mapped_status_is_written_and_scores_as_open(tmp_path):
    original = item_text(1, status="OPEN")
    cfg, backlog = _project(tmp_path, {1: original, 2: item_text(2)})
    control = _item_path(backlog, 2).read_bytes()
    assert not _fixture_scores_as_open(cfg, 1)  # known-bad arm: before the repair the scorer cannot read it
    report = _run(cfg, {"status_map": ["OPEN->IN_PROGRESS"]})
    assert report.state == "migrated", report.detail
    assert (report.generator_write_exit, report.generator_check_exit) == (0, 0)
    assert _item_path(backlog, 1).read_bytes() == original.replace(b"status: OPEN\n", b"status: IN_PROGRESS\n")
    assert _item_path(backlog, 2).read_bytes() == control
    assert _fixture_scores_as_open(cfg, 1)
    assert report.counts == {"status": 1} and report.refused == {} and report.remaining == {}
    assert not _archived(backlog, 1).exists()
    assert scan_item_shapes(backlog).classes["status-invalid"] == []


def test_a_quoted_status_line_is_replaced_whole_and_crlf_stays(tmp_path):
    original = item_text(1, status='"OPEN"', eol="\r\n")
    cfg, backlog = _project(tmp_path, {1: original})
    report = _run(cfg, {"status_map": ["OPEN->NOT_STARTED"]})
    assert report.state == "migrated", report.detail
    data = _item_path(backlog, 1).read_bytes()
    assert data == original.replace(b'status: "OPEN"\r\n', b"status: NOT_STARTED\r\n")
    assert data.count(b"\r\n") == data.count(b"\n")


def test_an_unanswered_status_is_refused_and_its_file_is_not_written(tmp_path):
    odd = item_text(1, status="OPEN", footer=None)  # a mechanical drift too: the file stays whole
    cfg, backlog = _project(tmp_path, {1: odd, 2: item_text(2, status="DONE")})
    before = _snapshot(backlog.parent)
    for answers in (None, {}, {"status_map": ["TODO->NOT_STARTED"]}):
        report = _run(cfg, answers)
        assert report.state == "clean" and report.refused == {"DONE": ["002"], "OPEN": ["001"]}
        assert _snapshot(backlog.parent) == before  # no file, backup or index was written
        assert report.backed_up == [] and report.written == []
        notes = [n for n in report.notes if "has no answer" in n]
        assert len(notes) == 2 and all("status_map" in n and "re-run /planwise upgrade" in n for n in notes)
        assert any("'OPEN'" in n and "001" in n and '"OPEN->NOT_STARTED"' in n for n in notes)


def test_an_unanswered_status_does_not_block_an_answered_one(tmp_path):
    cfg, backlog = _project(tmp_path, {1: item_text(1, status="OPEN"), 2: item_text(2, status="DONE")})
    odd = _item_path(backlog, 2).read_bytes()
    report = _run(cfg, {"status_map": ["OPEN->NOT_STARTED"]})
    assert report.state == "migrated" and report.refused == {"DONE": ["002"]}
    assert b"status: NOT_STARTED\n" in _item_path(backlog, 1).read_bytes()
    assert _item_path(backlog, 2).read_bytes() == odd
    assert set(report.remaining) == {"status-invalid"} and report.remaining["status-invalid"] == ["002"]


def test_a_status_mapped_to_a_closed_status_moves_the_file_to_archive(tmp_path):
    original = item_text(1, status="DONE")
    cfg, backlog = _project(tmp_path, {1: original, 2: item_text(2, status="WONTFIX"), 3: item_text(3)})
    report = _run(cfg, {"status_map": ["DONE->COMPLETE", "WONTFIX->CLOSED"]})
    assert report.state == "migrated", report.detail
    assert (report.generator_write_exit, report.generator_check_exit) == (0, 0)  # the regenerated index passes --check
    assert not _item_path(backlog, 1).exists() and not _item_path(backlog, 2).exists()
    assert _item_path(backlog, 3).is_file()
    assert _archived(backlog, 1).read_bytes() == original.replace(b"status: DONE\n", b"status: COMPLETE\n")
    assert b"status: CLOSED\n" in _archived(backlog, 2).read_bytes()
    assert report.counts == {"status": 2, "archived": 2}
    assert [r for r in report.routes if r[0] in ("001", "002")] == [("001", "?", "archived"), ("002", "?", "archived")]
    backup = backlog.parent / "upgrade-backups" / "1.0-to-1.1" / "backlog-items" / "BB-001-01-INFRA-Fixture.md"
    assert backup.read_bytes() == original  # the pre-image of the moved file is kept byte-exact
    again = _run(cfg, {"status_map": ["DONE->COMPLETE", "WONTFIX->CLOSED"]})
    assert again.state == "clean" and again.written == []


def test_the_banner_names_the_mapped_and_archived_counts(tmp_path, capsys):
    cfg, _backlog = _project(tmp_path, {1: item_text(1, status="OPEN"), 2: item_text(2, status="DONE"),
                                         3: item_text(3, status="LATER")})
    report = _run(cfg, {"status_map": ["OPEN->NOT_STARTED", "DONE->COMPLETE"]})
    mbi._emit_backlog_items_banner(report)
    out = capsys.readouterr().out
    assert "statuses mapped 2" in out and "items archived 1" in out and "002: ? -> archived" in out
    assert "action: 003: the status 'LATER' has no answer, so its file was not written" in out


def test_a_failed_archive_move_restores_every_file(tmp_path):
    cfg, backlog = _project(tmp_path, {1: item_text(1, status="OPEN", footer=None), 2: item_text(2, status="DONE")})
    squatter = _archived(backlog, 2)
    squatter.write_bytes(b"an earlier archived item with the same name\n")
    before = _snapshot(backlog.parent)
    report = _run(cfg, {"status_map": ["OPEN->NOT_STARTED", "DONE->COMPLETE"]})
    assert report.state == "write_failed" and "could not archive BB-002" in report.detail
    assert "destination already exists" in report.detail and "restored" in report.detail
    after = {k: v for k, v in _snapshot(backlog.parent).items() if not k.startswith("upgrade-backups/")}
    assert after == before  # both item files are back to their bytes, and the squatter was not replaced


def test_a_raising_status_map_never_fails_the_report(tmp_path):
    cfg, _backlog = _project(tmp_path, {1: item_text(1, status="OPEN")})
    for answers in ({"status_map": "OPEN->NOT_STARTED"}, {"status_map": [7, None, "OPEN"]}, {"status_map": None}):
        report = _run(cfg, answers)
        assert report.state == "clean" and report.refused == {"OPEN": ["001"]}  # a bad entry maps nothing


def _spy_on_the_call_sites(monkeypatch):
    calls = []
    monkeypatch.setattr(artifact_upgrade, "migrate_backlog_items",
                        lambda cfg, *args: calls.append(args) or mbi.ItemRepairReport(state="absent", index_path=None))
    monkeypatch.setattr(artifact_upgrade, "INSTALLED_RULES", [])
    return calls


def test_both_upgrade_exits_call_the_repair_after_the_index_retrofit(tmp_path, monkeypatch):
    calls = _spy_on_the_call_sites(monkeypatch)
    cfg, _backlog = _legacy_project(tmp_path / "main", pinned="1.0.5.1")
    assert artifact_upgrade._run_upgrade(cfg) == 0
    cfg, _backlog = _legacy_project(tmp_path / "current", pinned=TARGET_VERSION)
    assert artifact_upgrade._run_upgrade(cfg) == 0
    assert [args[0] for args in calls] == ["1.0.5.1", TARGET_VERSION]


def test_a_raising_repair_never_changes_either_exit_code(tmp_path, monkeypatch, capsys):
    def boom(*_args):
        raise RuntimeError("boom")

    monkeypatch.setattr(artifact_upgrade, "migrate_backlog_items", boom)
    monkeypatch.setattr(artifact_upgrade, "INSTALLED_RULES", [])
    for pinned in ("1.0.5.1", TARGET_VERSION):
        cfg, _backlog = _legacy_project(tmp_path / pinned, pinned=pinned)
        assert artifact_upgrade._run_upgrade(cfg) == 0
    assert capsys.readouterr().err.count("backlog item shape repair raised unexpectedly: boom") == 2
