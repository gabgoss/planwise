"""Tests for backlog_migration.py: the upgrade/init orchestrator around the
backlog index migrator. One test per report state, plus the config-path,
within-budget no-op and idempotence cases. Fixtures live under tmp_path,
never under plugins/planwise/, and are written as bytes."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import backlog_migration as bm
import config_loader
import generate_backlog_index as gen
import migrate_backlog_index as mig
import migrate_backlog_support as sup
import upgrade_io
from backlog_index_budget import _measure
from config_gen import InitConfig
from read_limits import READ_TOKEN_WARN

TITLE = "Sample item needs love"
DUP = "This extra detail duplicates content already present in the item file for dedup testing purposes."
NEW = "This extra detail is brand new prose the item file has never mentioned anywhere at all today."
AMBIG = "Alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima mike."
AMBIG_BODY = "Alpha bravo charlie delta echo foxtrot golf then something unrelated follows."
BULLET = "- 002 relates loosely to 001 through the shared sprocket configuration."
HEADER = "| ID | Feature | Priority | Status | Abbrev | Files |\n|---|---|---|---|---|---|\n"
FOOTER = "*Last Updated: 2024-01-01 — did something. Prior entry: 2023-12-01 — did something else.*\n"
INDEX = "00-Index-Backlog.md"
HEADER_ONLY = f"[← {INDEX}]({INDEX})\n"
CONFIG = ('project:\n  name: "test-project"\n  backlog_dir: "Backlog"\n  index_files:\n'
          f'    backlog: "{INDEX}"\nabbreviations:\n  SMP: Sample work\n  INFRA: Infrastructure and DevOps\n')
MIGRATED_HUB = ("Generated: 2024-01-01\n\n| ID | Title | Priority | Status | Domain | Created | Blocks | Score | File |\n"
                "|---|---|---|---|---|---|---|---|---|\n")
PARTIAL = '---\r\nid: 004\r\ntitle: "Partial item"\r\n---\r\n\r\n# Partial\r\n\r\nPartial body.\r\n'
BARE = "# Third\n\nThird body, with no frontmatter at all.\n"


def item_text(item_id="001", body=DUP, blocks="[]"):
    fm = [f"id: {item_id}", f"title: {TITLE}", "priority: High", "status: NOT_STARTED", "abbrev: SMP",
          "created: 2024-01-01", f"blocks: {blocks}"]
    return "\n".join(["---", *fm, "---", "", "# Sample Item", "", body, ""])


def legacy_index(feature1=f"{TITLE}. {DUP} {NEW}", header=HEADER):
    rows = (f"| 001 | {feature1} | High | NOT_STARTED | SMP | [001](001-Sample.md) |\n"
            f"| 002 | {TITLE} | High | NOT_STARTED | SMP | [002](Archive/ITEM-002-SMP-Other.md) |\n"
            "| 003 | Third item | Medium | NOT_STARTED | INFRA | [003](ITEM-003-INFRA-Third.md) |\n"
            "| 004 | Partial item | Low | NOT_STARTED | SMP | [004](ITEM-004-SMP-Partial.md) |\n")
    deps = f"## Dependencies\n\n| ID | Blocks |\n|---|---|\n| 001 | 002 |\n\n**Soft dependencies**\n\n{BULLET}\n\n"
    return f"## Backlog Items\n\n{header}{rows}\n{deps}---\n\n{FOOTER}"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def _project(tmp_path, index_text=None, body1=DUP, git=False):
    root = tmp_path / "proj"
    backlog = root / "planwise" / "Backlog"
    _write(root / "planwise" / "config.yaml", CONFIG)
    _write(backlog / INDEX, legacy_index() if index_text is None else index_text)
    _write(backlog / "00-Changelog-Backlog.md", HEADER_ONLY)
    _write(backlog / "001-Sample.md", item_text(body=body1))
    _write(backlog / "Archive" / "ITEM-002-SMP-Other.md", item_text("002", "Other item."))
    _write(backlog / "ITEM-003-INFRA-Third.md", BARE)
    _write(backlog / "ITEM-004-SMP-Partial.md", PARTIAL)
    if git:
        _write(root / "README.md", "fixture\n")
        for argv in (["init", "-q"], ["add", "-A"],
                     ["-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-q", "-m", "init"]):
            subprocess.run(["git", *argv], cwd=str(root), check=True, capture_output=True)
        _write(root / "README.md", "fixture, edited after the commit\n")
    cfg = InitConfig(project_name="test-project", project_root=root, plugin_root=SCRIPTS.parent)
    return cfg, backlog


def _snapshot(root: Path) -> dict:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*")
            if p.is_file() and ".git" not in p.parts}


def _pair(cfg, pair="1.0-to-1.1") -> Path:
    return cfg.project_root / "planwise" / "upgrade-backups" / pair


def _changelog_files(backlog: Path) -> list:
    pattern = sup.changelog_part_pattern(gen._index_naming(backlog / INDEX))
    return [backlog / "00-Changelog-Backlog.md"] + sorted(p for p in backlog.iterdir() if pattern.match(p.name))


def _migrate(cfg, pair=("1.0", "1.1"), **kwargs):
    return bm.migrate_backlog_if_legacy(cfg, *pair, **kwargs)


def test_legacy_index_migrates_with_byte_exact_backups(tmp_path):
    cfg, backlog = _project(tmp_path, git=True)
    before = _snapshot(backlog)
    report = _migrate(cfg)
    assert report.state == "migrated", report.detail
    assert (report.generator_write_exit, report.generator_check_exit) == (0, 0), report.detail
    assert sup.classify_shape(mig.read_text(backlog / INDEX))[0] == "migrated"
    backups = _pair(cfg) / "backlog"
    assert report.backup_dir == backups and len(report.backed_up) >= 5
    for rel in ("00-Index-Backlog.md", "00-Changelog-Backlog.md", "001-Sample.md", "Archive/ITEM-002-SMP-Other.md",
                "ITEM-003-INFRA-Third.md", "ITEM-004-SMP-Partial.md"):
        assert (backups / rel).read_bytes() == before[rel], rel
    dispositions = (_pair(cfg) / "DISPOSITIONS.md").read_text(encoding="utf-8")
    assert dispositions.count("backlog-migrated") == len(report.written) >= 6
    assert report.ledger_path is not None and report.ledger_path.is_file()
    c = report.counts
    assert (c["backfilled"], c["partial"], c["edges"], c["dependency_notes"], c["changelog_parts"]) == (2, 1, 1, 1, 1)
    assert c["prose_units"] >= 1 and c["changelog_entries"] == 2 and c["shards"] >= 0
    assert report.git_dirty is True
    crlf = (backlog / "ITEM-004-SMP-Partial.md").read_bytes()
    assert crlf.count(b"\n") == crlf.count(b"\r\n") and b"priority: Low\r\n" in crlf


def test_abbreviation_is_backfilled_against_the_configured_mapping(tmp_path):
    cfg, backlog = _project(tmp_path)
    report = _migrate(cfg)
    assert report.state == "migrated", report.detail
    third = (backlog / "ITEM-003-INFRA-Third.md").read_text(encoding="utf-8")
    assert third.startswith("---\n") and "\nabbrev: INFRA\n" in third and "\nid: 003\n" in third
    # Control: a lowercase cell that matches no configured key refuses (the upgrade adds only uppercase
    # names to the config), so the assertion above rests on the configured keys, not on the file name alone.
    control = legacy_index().replace("| NOT_STARTED | SMP | [001]", "| NOT_STARTED | core | [001]")
    cfg2, _backlog2 = _project(tmp_path / "control", control)
    refused = _migrate(cfg2)
    assert refused.state == "refused" and "abbrev" in refused.detail, refused.detail


def test_header_only_changelog_is_filled(tmp_path):
    cfg, backlog = _project(tmp_path)
    assert (backlog / "00-Changelog-Backlog.md").read_bytes() == HEADER_ONLY.encode()
    assert _migrate(cfg).state == "migrated"
    log = (backlog / "00-Changelog-Backlog.md").read_text(encoding="utf-8")
    assert "did something else" in log and "did something." in log


def test_second_call_after_migrated_is_generated_and_touches_nothing(tmp_path):
    cfg, _backlog = _project(tmp_path)
    assert _migrate(cfg).state == "migrated"
    after = _snapshot(tmp_path)
    again = _migrate(cfg, ("1.1", "1.2"))
    assert again.state == "generated" and _snapshot(tmp_path) == after


def test_ambiguous_unit_is_parked_in_the_ledger_not_appended(tmp_path, capsys):
    cfg, backlog = _project(tmp_path, legacy_index(f"{TITLE}. {AMBIG}"), body1=AMBIG_BODY)
    item_before = (backlog / "001-Sample.md").read_bytes()
    report = _migrate(cfg)
    bm._emit_backlog_migration_banner(report)
    banner = capsys.readouterr().out
    assert report.state == "migrated", report.detail
    # The unit is kept verbatim in the ledger, with its row, target, score and size.
    ledger = json.loads(mig.read_text(report.ledger_path))
    [parked] = ledger["parked_ambiguous"]
    assert parked["unit"] == AMBIG and parked["row"] == "001" and parked["bytes"] == len(AMBIG.encode("utf-8"))
    assert Path(parked["path"]).name == "001-Sample.md" and sup.DEFAULT_LOW < parked["similarity"] <= 1
    assert (ledger["dedup"]["parked_units"], ledger["dedup"]["parked_bytes"]) == (1, parked["bytes"])
    assert (ledger["dedup"]["unaccounted_units"], ledger["dedup"]["unaccounted_bytes"]) == (0, 0)
    assert ledger["changelog"]["unaccounted"] == 0 and ledger["verification"]["verified"] is True
    # Nothing is appended: the item's body is unchanged (only its blocks: line gains the edge).
    item_after = (backlog / "001-Sample.md").read_text(encoding="utf-8")
    assert AMBIG not in item_after and sup.NOTES_HEADING not in item_after
    assert item_after.replace("blocks: [002]", "blocks: []") == item_before.decode("utf-8")
    assert f"parked ambiguous units: 1 ({parked['bytes']} bytes) — see {report.ledger_path}" in banner, banner
    # A re-run is silent and changes nothing.
    after = _snapshot(tmp_path)
    again = _migrate(cfg, ("1.1", "1.2"))
    assert again.state == "generated", again.detail
    assert _snapshot(tmp_path) == after


def test_parked_units_survive_a_crash_between_the_index_write_and_the_ledger_write(tmp_path, monkeypatch, capsys):
    cfg, backlog = _project(tmp_path, legacy_index(f"{TITLE}. {AMBIG}"), body1=AMBIG_BODY)
    ledger_path = backlog / "00-Index-Backlog-Migration-Ledger.json"

    def crash(*args, **kwargs):
        raise RuntimeError("simulated crash after the index was replaced, before the ledger write")
    with monkeypatch.context() as m:
        m.setattr(mig, "build_ledger", crash)
        crashed = _migrate(cfg)
    assert crashed.state == "error" and "simulated crash" in crashed.detail
    index = mig.read_text(backlog / INDEX)
    assert sup.POINTER_RE.match(sup.FOOTER_TEXT_RE.search(index)[0])  # the index was replaced
    # The journal, replaced first, is the parked unit's only home now -- and it holds it verbatim.
    journal = json.loads(mig.read_text(ledger_path))
    assert journal["mode"] == sup.JOURNAL_MODE
    assert [(p["row"], p["unit"]) for p in journal["parked_ambiguous"]] == [("001", AMBIG)]
    # A rerun must not regenerate over it: it renames the journal to a dated sibling, keeps every byte
    # of it, logs the rename, and finishes the migration.
    journal_bytes = ledger_path.read_bytes()
    # Why the parked unit cannot be re-derived: the crashed run already replaced the index, so the plan is None.
    config = config_loader.load_config(Path(bm.__file__), config_path=backlog.parent / "config.yaml")
    text = mig.read_text(backlog / INDEX)
    assert mig.plan_migration(config, backlog / INDEX, text, sup.classify_shape(text)[1],
                              mig.RepairOptions.unattended()) is None
    again = _migrate(cfg)
    assert again.state == "migrated", again.detail
    kept = ledger_path.with_name(f"{ledger_path.stem}-Interrupted-{mig._today()}.json")
    assert kept.read_bytes() == journal_bytes and AMBIG in kept.read_text(encoding="utf-8")
    assert again.counts["journal_renamed_to"] == str(kept)
    note = json.loads(mig.read_text(ledger_path))
    assert note["mode"] == "journal-renamed" and note["journal_renamed_to"] == str(kept)
    assert note["parked_units_in_journal"] == 1 and "remain verbatim in the renamed journal and need review" in note["note"]
    assert "re-derived" not in note["note"].replace("did not re-derive", "")
    bm._emit_backlog_migration_banner(again)
    assert f"    interrupted journal:    renamed to {kept}; its 1 parked unit(s) remain there and need review" in capsys.readouterr().out
    rows = (_pair(cfg) / "DISPOSITIONS.md").read_text(encoding="utf-8")
    assert f"interrupted journal renamed from {ledger_path.name}; pre-image at upgrade-backups/1.0-to-1.1/backlog/" in rows
    assert (_pair(cfg) / "backlog" / ledger_path.name).read_bytes() == journal_bytes


def test_standalone_cli_still_refuses_an_ambiguous_unit_by_default(tmp_path):
    cfg, _backlog = _project(tmp_path, legacy_index(f"{TITLE}. {AMBIG}"), body1=AMBIG_BODY)
    before = _snapshot(tmp_path)
    flags = ["--backfill-frontmatter", "--write-edges", "--extract-dependency-notes", "--reconcile", "index-wins",
             "--allow-untracked-tree", "--force", "--write"]
    proc = subprocess.run([sys.executable, str(SCRIPTS / "migrate_backlog_index.py"), "--config",
                           str(cfg.project_root / "planwise" / "config.yaml"), *flags],
                          capture_output=True, text=True, check=False,
                          env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "1 ambiguous dedup unit(s)" in proc.stderr and "--append-ambiguous" in proc.stderr
    assert _snapshot(tmp_path) == before


def test_append_ambiguous_wins_over_parking(tmp_path):
    cfg, _backlog = _project(tmp_path, legacy_index(f"{TITLE}. {AMBIG}"), body1=AMBIG_BODY)
    config = config_loader.load_config(Path(bm.__file__), config_path=cfg.project_root / "planwise" / "config.yaml")
    index_path = config["_index_path"]
    text = mig.read_text(index_path)
    detail = sup.classify_shape(text)[1]
    both = mig.RepairOptions.unattended()
    both.append_ambiguous = True
    plan = mig.plan_migration(config, index_path, text, detail, both)
    dest = next(d for d in plan["dests"] if d["path"].name == "001-Sample.md")
    assert dest["parked"] == [] and dest["ambiguous"] == [AMBIG]
    assert AMBIG in dict(plan["outputs"])[dest["path"]]
    parked = mig.plan_migration(config, index_path, text, detail, mig.RepairOptions.unattended())
    assert [p["unit"] for d in parked["dests"] for p in d["parked"]] == [AMBIG]


def test_every_newly_created_file_gets_a_created_disposition_row(tmp_path):
    # Item 002 is COMPLETE, so the generator writes an Archive shard that did not exist before.
    cfg, backlog = _project(tmp_path, legacy_index().replace("| NOT_STARTED | SMP | [002]", "| COMPLETE | SMP | [002]"))
    other = backlog / "Archive" / "ITEM-002-SMP-Other.md"
    _write(other, other.read_text(encoding="utf-8").replace("status: NOT_STARTED", "status: COMPLETE"))
    existed = {p.resolve() for p in backlog.rglob("*") if p.is_file()}
    report = _migrate(cfg)
    assert report.state == "migrated", report.detail
    rows = {}  # resolved path -> its DISPOSITIONS row; a row reads "- {date} `{rel}` — {action}: {reason}"
    for r in (_pair(cfg) / "DISPOSITIONS.md").read_text(encoding="utf-8").splitlines():
        if "backlog-migrated" in r:
            rows.setdefault((cfg.project_root / r.split("`")[1]).resolve(), []).append(r)
    assert sorted(rows) == sorted({Path(p).resolve() for p in report.written})
    created = [Path(p).resolve() for p in report.written if Path(p).resolve() not in existed]
    # The ledger is always new here, and the generator adds at least one Archive shard.
    assert report.ledger_path.resolve() in created
    assert any(p.parent.name == "Archive" for p in created), report.written
    for path in created:
        [row] = rows[path]
        assert "created; no pre-image" in row, row
    for path in (Path(p).resolve() for p in report.written if Path(p).resolve() in existed):
        assert not any("created; no pre-image" in r for r in rows[path]), rows[path]


def test_banner_names_relocated_index_lines(tmp_path, capsys):
    preamble, note = "Intro prose before the heading.", "> note: keep the sprocket ids stable."
    index = "# Backlog\n\n" + preamble + "\n\n" + legacy_index().replace(
        "Partial.md) |\n\n## Dependencies", f"Partial.md) |\n\n{note}\n\n## Dependencies")
    assert note in index
    cfg, backlog = _project(tmp_path, index)
    report = _migrate(cfg)
    bm._emit_backlog_migration_banner(report)
    banner = capsys.readouterr().out
    assert report.state == "migrated", report.detail
    ledger = json.loads(mig.read_text(report.ledger_path))
    size = len(preamble.encode("utf-8")) + len(note.encode("utf-8"))
    assert sorted(r["bytes"] for r in ledger["relocated_index_lines"]) == sorted([len(preamble), len(note)])
    line = f"    relocated index lines:  2 ({size} bytes) into {ledger['changelog']['path']}"
    assert line in banner.splitlines(), banner
    assert ledger["changelog"]["unaccounted"] == 0
    log = (backlog / "00-Changelog-Backlog.md").read_text(encoding="utf-8")
    assert preamble in log and note in log and "Relocated index text (migrated " in log


def test_unknown_owner_bullet_relocates(tmp_path):
    bullet = BULLET.replace("002", "099", 1)
    cfg, backlog = _project(tmp_path, legacy_index().replace(BULLET, bullet))
    report = _migrate(cfg)
    assert report.state == "migrated", report.detail
    ledger = json.loads(mig.read_text(report.ledger_path))
    assert [r["kind"] for r in ledger["relocated_index_lines"]] == ["unknown-owner bullet"]
    log = (backlog / "00-Changelog-Backlog.md").read_text(encoding="utf-8")
    assert f"(unknown-owner bullet): {bullet}" in log
    assert ledger["changelog"]["unaccounted"] == 0 and ledger["verification"]["verified"] is True


def test_unrecognized_shape_is_reported_and_untouched(tmp_path):
    header = HEADER.replace("| Files |", "| Owner | Files |")
    cfg, _backlog = _project(tmp_path, legacy_index(header=header))
    before = _snapshot(tmp_path)
    report = _migrate(cfg)
    assert report.state == "unrecognized" and "Owner" in report.detail
    assert report.fix.endswith("--report") and "migrate_backlog_index.py --config" in report.fix
    assert _snapshot(tmp_path) == before


def test_failed_backup_writes_nothing(tmp_path, monkeypatch):
    cfg, _backlog = _project(tmp_path)
    before = _snapshot(tmp_path)

    def refuse_copy(src, dst):
        raise OSError("simulated full disk")
    monkeypatch.setattr(upgrade_io, "_copy_bytes_exact", refuse_copy)
    report = _migrate(cfg)
    assert report.state == "backup_failed" and "simulated full disk" in report.detail
    assert _snapshot(tmp_path) == before


def test_failed_write_is_reported_after_the_backup(tmp_path, monkeypatch):
    cfg, _backlog = _project(tmp_path)
    monkeypatch.setattr(mig, "execute", lambda *args: print("FAIL: simulated") or 1)
    report = _migrate(cfg)
    assert report.state == "write_failed" and "FAIL: simulated" in report.detail
    assert report.backed_up and report.generator_write_exit is None


def test_unexpected_exception_becomes_state_error(tmp_path, monkeypatch):
    cfg, _backlog = _project(tmp_path)
    before = _snapshot(tmp_path)

    def boom(*args, **kwargs):
        raise RuntimeError("injected failure")
    monkeypatch.setattr(mig, "plan_migration", boom)
    report = _migrate(cfg)
    assert report.state == "error" and "injected failure" in report.detail
    assert _snapshot(tmp_path) == before


def test_missing_config_or_index_is_absent(tmp_path):
    root = tmp_path / "empty"
    root.mkdir()
    cfg = InitConfig(project_name="x", project_root=root, plugin_root=SCRIPTS.parent)
    assert _migrate(cfg).state == "absent"
    _write(root / "planwise" / "config.yaml", CONFIG)
    assert _migrate(cfg).state == "absent" and not (root / "planwise" / "upgrade-backups").exists()


def test_generated_hub_without_changelog_is_silent(tmp_path, capsys):
    cfg, backlog = _project(tmp_path, MIGRATED_HUB)
    (backlog / "00-Changelog-Backlog.md").unlink()
    before = _snapshot(tmp_path)
    report = _migrate(cfg)
    bm._emit_backlog_migration_banner(report)
    assert report.state == "generated" and capsys.readouterr().out == ""
    assert _snapshot(tmp_path) == before


def test_generated_hub_with_changelog_within_budget_writes_nothing(tmp_path):
    cfg, backlog = _project(tmp_path, MIGRATED_HUB)
    part2 = sup.changelog_part_filename(gen._index_naming(backlog / INDEX), 2)
    _write(backlog / "00-Changelog-Backlog.md", f"{HEADER_ONLY}\nParts: [{part2}]({part2})\n\n## Entry 1\n\nOne.\n")
    _write(backlog / part2, "[← 00-Changelog-Backlog.md](00-Changelog-Backlog.md)\n\n## Entry 2\n\nTwo.\n")
    before = _snapshot(tmp_path)
    assert _migrate(cfg).state == "generated"
    assert _snapshot(tmp_path) == before and not (cfg.project_root / "planwise" / "upgrade-backups").exists()


def test_over_budget_changelog_is_resplit_with_backups(tmp_path):
    cfg, backlog = _project(tmp_path)
    assert _migrate(cfg).state == "migrated"
    part1 = backlog / "00-Changelog-Backlog.md"
    paragraphs = "\n\n".join(f"Paragraph {i}: " + "growth of the changelog after migration. " * 9 for i in range(320))
    _write(part1, mig.read_text(part1) + f"## Entry 3\n\n{paragraphs}\n\n")
    stale = backlog / sup.changelog_part_filename(gen._index_naming(backlog / INDEX), 9)
    _write(stale, f"[← {part1.name}]({part1.name})\n\n## Entry 4\n\nStale part text kept by the re-split.\n")
    assert _measure(mig.read_text(part1))[1] > READ_TOKEN_WARN
    before = _snapshot(backlog)
    report = _migrate(cfg, ("1.1", "1.2"))
    assert report.state == "changelog_split", report.detail
    assert 2 <= report.counts["changelog_parts"] < 9 and not stale.exists()
    files = _changelog_files(backlog)
    assert len(files) == report.counts["changelog_parts"]
    assert all(_measure(mig.read_text(p).replace("\r\n", "\n"))[1] <= READ_TOKEN_WARN for p in files)
    assert sum(mig.read_text(p).count("Stale part text kept") for p in files) == 1
    backups = _pair(cfg, "1.1-to-1.2") / "backlog"
    assert (backups / part1.name).read_bytes() == before[part1.name]
    assert (backups / stale.name).read_bytes() == before[stale.name]
    rows = (_pair(cfg, "1.1-to-1.2") / "DISPOSITIONS.md").read_text(encoding="utf-8")
    assert rows.count("backlog-changelog-split") == len(report.written) == len(files) + 1
    after = _snapshot(tmp_path)
    assert _migrate(cfg, ("1.2", "1.3")).state == "generated" and _snapshot(tmp_path) == after


def test_failed_resplit_write_is_reported_after_the_backup(tmp_path, monkeypatch):
    cfg, backlog = _project(tmp_path, MIGRATED_HUB)
    body = "\n\n".join(f"Paragraph {i}: " + "growth of the changelog after migration. " * 9 for i in range(320))
    _write(backlog / "00-Changelog-Backlog.md", f"{HEADER_ONLY}\n## Entry 1\n\n{body}\n\n")
    before = _snapshot(backlog)

    def fail(*args):
        raise OSError("simulated staging failure")
    monkeypatch.setattr(mig, "execute_outputs", fail)
    report = _migrate(cfg)
    assert report.state == "write_failed" and "simulated staging failure" in report.detail
    assert report.backed_up and _snapshot(backlog) == before


@pytest.mark.parametrize("state,headline", [
    ("migrated", "Backlog index migration:"),
    ("changelog_split", "Backlog changelog: re-split into 3 part(s)"),
    ("refused", "Backlog index migration: REFUSED"),
    ("unrecognized", "is not a hand-authored or generated index"),
    ("backup_failed", "Backlog index migration: BACKUP FAILED"),
    ("write_failed", "Backlog index migration: WRITE FAILED"),
    ("error", "Backlog index migration: ERROR"),
])
def test_banner_names_each_state(capsys, state, headline):
    report = bm.BacklogMigrationReport(state=state, index_path=Path("Backlog") / INDEX, detail="why",
                                       fix="do this\n" + bm.RERUN, counts={"changelog_parts": 3, "shards": 1},
                                       generator_write_exit=0, generator_check_exit=0, git_dirty=False)
    bm._emit_backlog_migration_banner(report)
    out = capsys.readouterr().out
    assert headline in out.splitlines()[0]
    if state == "refused":
        assert "  fix:    do this" in out and "then re-run /planwise upgrade" in out
    if state == "migrated":
        assert "generator --check:      clean" in out and "git tree was dirty:     no" in out


def test_backlog_deferred_fix_names_no_flag(tmp_path):
    cfg, _backlog = _project(tmp_path)
    report = _migrate(cfg, defer_legacy=True)
    assert report.state == "deferred", report.detail
    assert report.fix and "--" not in report.fix


def test_refused_fix_line_names_an_edit(tmp_path):
    # Rows 001 and 002 block each other, and item 002's own frontmatter blocks 001: a reciprocal pair.
    header = "| ID | Feature | Priority | Status | Abbrev | Blocks | Files |\n|---|---|---|---|---|---|---|\n"
    rows = (f"| 001 | {TITLE}. {DUP} | High | NOT_STARTED | SMP | 002 | [001](001-Sample.md) |\n"
            f"| 002 | {TITLE} | High | NOT_STARTED | SMP | 001 | [002](Archive/ITEM-002-SMP-Other.md) |\n"
            "| 003 | Third item | Medium | NOT_STARTED | INFRA |  | [003](ITEM-003-INFRA-Third.md) |\n"
            "| 004 | Partial item | Low | NOT_STARTED | SMP |  | [004](ITEM-004-SMP-Partial.md) |\n")
    cfg, backlog = _project(tmp_path, f"## Backlog Items\n\n{header}{rows}\n---\n\n{FOOTER}")
    _write(backlog / "Archive" / "ITEM-002-SMP-Other.md", item_text("002", "Other item.", blocks="[001]"))
    report = _migrate(cfg)
    assert report.state == "refused" and "reciprocal" in report.detail, (report.state, report.detail)
    assert "remove the other item's id" in report.fix
    assert "remove the other item's id" not in report.detail


@pytest.mark.parametrize("state", ["absent", "generated"])
def test_banner_is_silent_when_nothing_happened(capsys, state):
    bm._emit_backlog_migration_banner(bm.BacklogMigrationReport(state=state, index_path=None))
    assert capsys.readouterr().out == ""


def test_load_config_config_path_ignores_argv(tmp_path, monkeypatch):
    real = tmp_path / "real" / "planwise" / "config.yaml"
    decoy = tmp_path / "decoy" / "planwise" / "config.yaml"
    _write(real, CONFIG)
    _write(decoy, CONFIG.replace('backlog_dir: "Backlog"', 'backlog_dir: "Elsewhere"'))
    monkeypatch.setattr(sys, "argv", ["script.py", "--config", str(decoy)])
    config = config_loader.load_config(config_path=real)
    assert config["_backlog_dir"] == real.resolve().parent / "Backlog"
    assert config["_index_path"].name == INDEX and "INFRA" in config["abbreviations"]
    assert config_loader.load_config()["_backlog_dir"].name == "Elsewhere"
    with pytest.raises(FileNotFoundError):
        config_loader.load_config(config_path=tmp_path / "missing" / "config.yaml")


def test_ledger_counts_are_left_unset_while_the_journal_is_in_progress(tmp_path):
    ledger = tmp_path / "ledger.json"
    ledger.write_bytes(json.dumps({"mode": sup.JOURNAL_MODE, "targets": []}).encode("utf-8"))
    report = bm.BacklogMigrationReport(state="migrated", index_path=None)
    bm._fill_counts(ledger, "index-wins", report)
    assert report.counts == {} and "write-in-progress" in report.detail
