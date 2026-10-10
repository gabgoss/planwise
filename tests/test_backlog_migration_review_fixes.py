"""Regression tests for the backlog migration orchestrator's failure and
re-run paths: rollback on a failed write, first-pre-image-wins backups, the
already-migrated regeneration path, a tolerant ledger read, backups of the
generated files the index write replaces, the generator's pointer-footer
guard and refusal messages, a byte-order mark on changelog part 1, and the
backup path each DISPOSITIONS row names. Fixtures come from the orchestrator
suite's own builders: bytes under tmp_path, never under plugins/planwise/."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_backlog_migration as base
from test_backlog_migration import bm, config_loader, gen, mig, sup

CHANGELOG = "00-Changelog-Backlog.md"
POINTER_INDEX = base.legacy_index().replace(base.FOOTER, "*Last Updated: 2024-02-01 — moved to [{0}]({0})*\n")
UNRECOGNIZED = "# Backlog\n\n| Foo | Bar |\n|---|---|\n| 1 | 2 |\n"
POPULATED = f"{base.HEADER_ONLY}\n## Entry 1\n\n 2024-01-01 — did something.\n\n"


def _over_budget(tmp_path, paragraphs=320, prefix=""):
    cfg, backlog = base._project(tmp_path, base.MIGRATED_HUB)
    body = "\n\n".join(f"Paragraph {i}: " + "growth of the changelog after migration. " * 9
                       for i in range(paragraphs))
    base._write(backlog / CHANGELOG, f"{prefix}{base.HEADER_ONLY}\n## Entry 1\n\n{body}\n\n")
    return cfg, backlog


def _fail_replace(monkeypatch, n, then=None):
    """Make the n-th staged replace raise; `then` runs just before it raises."""
    real, calls = sup._replace, []

    def replace(src, dst):
        calls.append(dst)
        if len(calls) == n:
            if then:
                then()
            raise OSError(f"simulated failure on replace {n}")
        return real(src, dst)
    monkeypatch.setattr(sup, "_replace", replace)


def _refuse_generator_write(monkeypatch):
    monkeypatch.setattr(gen, "_cmd_write", lambda *a, **k: print("Error: simulated generator refusal") or 2)


def _config(cfg):
    return config_loader.load_config(Path(bm.__file__), config_path=cfg.project_root / "planwise" / "config.yaml")


def _gen(config, mode, capsys):
    index = config["_index_path"]
    args = (config["_backlog_dir"], config["_archive_dir"], index, gen._index_naming(index), config)
    code = (gen._cmd_write if mode == "write" else gen._cmd_check)(*args, json_out=False)
    return code, capsys.readouterr().err


# --- a failed write restores the tree ---

def test_failed_second_replace_of_a_resplit_restores_the_tree(tmp_path, monkeypatch):
    cfg, backlog = _over_budget(tmp_path)
    before = base._snapshot(backlog)
    _fail_replace(monkeypatch, 2)
    report = base._migrate(cfg)
    assert report.state == "write_failed", report.detail
    assert "simulated failure on replace 2" in report.detail and "restored" in report.detail
    assert base._snapshot(backlog) == before


def test_failed_last_replace_of_a_resplit_deletes_the_new_parts(tmp_path, monkeypatch):
    cfg, backlog = _over_budget(tmp_path, paragraphs=700)
    n = len(sup.plan_changelog_resplit({}, backlog / base.INDEX)["outputs"])
    assert n >= 3
    before = base._snapshot(backlog)
    _fail_replace(monkeypatch, n)
    assert base._migrate(cfg).state == "write_failed"
    assert base._snapshot(backlog) == before


def test_failed_restore_names_the_backup_directory(tmp_path, monkeypatch):
    cfg, _backlog = _over_budget(tmp_path)

    def refuse_writes():
        def boom(self, data):
            raise OSError("simulated restore failure")
        monkeypatch.setattr(Path, "write_bytes", boom)
    _fail_replace(monkeypatch, 2, then=refuse_writes)
    report = base._migrate(cfg)
    assert report.state == "write_failed" and "restore failed" in report.detail
    assert str(report.backup_dir) in report.detail and str(report.backup_dir) in report.fix


def test_failed_migration_write_after_a_partial_replace_restores_the_tree(tmp_path, monkeypatch):
    cfg, backlog = base._project(tmp_path)
    before = base._snapshot(backlog)
    _fail_replace(monkeypatch, 3)  # the journal and one item file are already replaced
    report = base._migrate(cfg)
    assert report.state == "write_failed" and "restored" in report.detail, report.detail
    assert base._snapshot(backlog) == before


# --- the first pre-image wins ---

def test_same_pair_rerun_keeps_the_first_pre_images(tmp_path, monkeypatch):
    cfg, backlog = base._project(tmp_path)
    original = base._snapshot(backlog)
    with monkeypatch.context() as m:
        m.setattr(mig, "execute", lambda *a: print("FAIL: simulated") or 1)
        assert base._migrate(cfg).state == "write_failed"
    base._write(backlog / "ITEM-003-INFRA-Third.md", "# Third\n\nThird body, edited between the two runs.\n")
    report = base._migrate(cfg)
    assert report.state == "migrated", report.detail
    backups = base._pair(cfg) / "backlog"
    for rel in ("ITEM-003-INFRA-Third.md", base.INDEX, "001-Sample.md"):
        assert (backups / rel).read_bytes() == original[rel], rel
    rows = (base._pair(cfg) / "DISPOSITIONS.md").read_text(encoding="utf-8")
    assert "made by an earlier run in this version pair" in rows


def test_outside_paths_sharing_a_name_get_distinct_backup_paths(tmp_path):
    backlog = tmp_path / "Backlog"
    one, two = bm._rel(tmp_path / "one" / "X.md", backlog), bm._rel(tmp_path / "two" / "X.md", backlog)
    assert one != two and one.name == two.name == "X.md" and one != Path("X.md")
    assert bm._rel(tmp_path / "one" / "X.md", backlog) == one
    assert bm._rel(backlog / "Archive" / "Y.md", backlog) == Path("Archive") / "Y.md"


# --- the index the migrator already rewrote ---

def test_generator_refusal_after_the_migrator_write_is_write_failed(tmp_path, monkeypatch):
    cfg, backlog = base._project(tmp_path)
    _refuse_generator_write(monkeypatch)
    report = base._migrate(cfg)
    assert report.state == "write_failed" and report.generator_write_exit == 2
    assert "simulated generator refusal" in report.detail
    assert sup.classify_shape(mig.read_text(backlog / base.INDEX))[0] == "legacy"


def test_already_migrated_index_is_backed_up_before_regeneration(tmp_path, monkeypatch):
    cfg, backlog = base._project(tmp_path)
    with monkeypatch.context() as m:
        _refuse_generator_write(m)
        base._migrate(cfg)
    pointer_index = (backlog / base.INDEX).read_bytes()
    report = base._migrate(cfg, ("1.1", "1.2"))
    assert report.state == "migrated", report.detail
    assert (base._pair(cfg, "1.1-to-1.2") / "backlog" / base.INDEX).read_bytes() == pointer_index
    after = base._snapshot(tmp_path)
    assert base._migrate(cfg, ("1.2", "1.3")).state == "generated" and base._snapshot(tmp_path) == after


def test_already_migrated_index_reports_no_counts_from_an_earlier_ledger(tmp_path, monkeypatch):
    cfg, _backlog = base._project(tmp_path)
    with monkeypatch.context() as m:
        _refuse_generator_write(m)
        base._migrate(cfg)
    report = base._migrate(cfg, ("1.1", "1.2"))
    assert report.state == "migrated", report.detail
    assert "changelog_entries" not in report.counts and report.ledger_path is None


# --- a ledger in an older shape ---

def test_ledger_missing_a_key_leaves_counts_unset_and_the_state_migrated(tmp_path, monkeypatch):
    cfg, _backlog = base._project(tmp_path)
    real = mig.build_ledger

    def older_schema(*args, **kwargs):
        ledger = real(*args, **kwargs)
        del ledger["dependency_notes"]
        return ledger
    monkeypatch.setattr(mig, "build_ledger", older_schema)
    report = base._migrate(cfg)
    assert report.state == "migrated", report.detail
    assert "changelog_entries" not in report.counts and "counts left unset" in report.detail


def test_ledger_with_a_wrong_type_leaves_counts_unset(tmp_path):
    ledger = tmp_path / "ledger.json"
    ledger.write_bytes(json.dumps({"mode": "write", "changelog": [], "dependency_notes": [],
                                   "reconcile": {"cells": [], "mode": None}}).encode("utf-8"))
    report = bm.BacklogMigrationReport(state="migrated", index_path=None)
    bm._fill_counts(ledger, "index-wins", report)
    assert report.state == "migrated" and report.counts == {} and "counts left unset" in report.detail


# --- generated files the index write replaces or removes ---

def test_generated_files_the_write_removes_are_backed_up_first(tmp_path):
    cfg, backlog = base._project(tmp_path)
    stale = backlog / "Archive" / "Index-Backlog-900-950.md"
    base._write(stale, "stale shard from an older generator run\n")
    before = stale.read_bytes()
    report = base._migrate(cfg)
    assert report.state == "migrated", report.detail
    assert not stale.exists()
    assert (base._pair(cfg) / "backlog" / "Archive" / stale.name).read_bytes() == before
    rows = (base._pair(cfg) / "DISPOSITIONS.md").read_text(encoding="utf-8")
    assert ("backlog-migrated: regenerated or removed by the index generator; "
            f"pre-image at upgrade-backups/1.0-to-1.1/backlog/Archive/{stale.name}") in rows


# --- the generator's guard and refusal messages ---

def test_pointer_footer_to_a_foreign_changelog_is_refused(tmp_path, capsys):
    cfg, backlog = base._project(tmp_path, POINTER_INDEX.format("Other-Changelog.md"))
    index = backlog / base.INDEX
    assert sup.refuse_unless_generated(index, mig.read_text)[0] == "legacy"
    code, err = _gen(_config(cfg), "write", capsys)
    assert code == 2 and "hand-authored" in err
    base._write(index, POINTER_INDEX.format(CHANGELOG))
    base._write(backlog / CHANGELOG, POPULATED)
    assert sup.refuse_unless_generated(index, mig.read_text) is None


def test_pointer_footer_with_a_missing_changelog_is_refused(tmp_path, capsys):
    cfg, backlog = base._project(tmp_path, POINTER_INDEX.format(CHANGELOG))
    (backlog / CHANGELOG).unlink()
    before = base._snapshot(backlog)
    code, err = _gen(_config(cfg), "write", capsys)
    assert code == 2 and "hand-authored" in err
    assert base._snapshot(backlog) == before


def test_pointer_footer_with_a_header_only_changelog_is_refused(tmp_path, capsys):
    cfg, backlog = base._project(tmp_path, POINTER_INDEX.format(CHANGELOG))
    assert (backlog / CHANGELOG).read_bytes() == base.HEADER_ONLY.encode("utf-8")
    before = base._snapshot(backlog)
    code, err = _gen(_config(cfg), "write", capsys)
    assert code == 2 and "hand-authored" in err
    assert base._snapshot(backlog) == before
    base._write(backlog / CHANGELOG, POPULATED)  # control: the same pointer passes once the changelog is populated
    assert sup.refuse_unless_generated(backlog / base.INDEX, mig.read_text) is None


def test_unrecognized_index_refusal_names_the_reason_and_the_report(tmp_path, capsys):
    cfg, _backlog = base._project(tmp_path, UNRECOGNIZED)
    config = _config(cfg)
    for mode in ("write", "check"):
        code, err = _gen(config, mode, capsys)
        assert code == 2 and "hand-authored" not in err, mode
        assert "unrecognized index shape" in err and "'Foo'" in err, mode
        assert "migrate_backlog_index.py --config" in err and "--report" in err, mode
        assert str(Path(config["_planwise_root"]) / "config.yaml") in err, mode
        assert ("WITHOUT a backup" in err) == (mode == "write"), mode


def test_legacy_refusal_says_replace_legacy_has_no_backup(tmp_path, capsys):
    cfg, _backlog = base._project(tmp_path)
    config = _config(cfg)
    code, err = _gen(config, "write", capsys)
    assert code == 2 and "hand-authored index" in err and "/planwise upgrade" in err
    assert "--replace-legacy to overwrite it WITHOUT a backup" in err
    code, err = _gen(config, "check", capsys)
    assert code == 2 and "hand-authored index" in err and "/planwise upgrade" in err


# --- a byte-order mark on changelog part 1 ---

def test_bom_on_changelog_part_one_is_resplit_and_kept(tmp_path):
    cfg, backlog = _over_budget(tmp_path, prefix="\ufeff")
    report = base._migrate(cfg)
    assert report.state == "changelog_split", report.detail
    part1 = (backlog / CHANGELOG).read_bytes()
    assert part1.startswith("\ufeff[← ".encode("utf-8")) and part1.count("\ufeff".encode("utf-8")) == 1
    assert report.counts["changelog_parts"] >= 2


# --- DISPOSITIONS rows name the real backup path ---

def test_disposition_rows_name_the_real_backup_path(tmp_path):
    cfg, _backlog = base._project(tmp_path)
    assert base._migrate(cfg).state == "migrated"
    rows = (base._pair(cfg) / "DISPOSITIONS.md").read_text(encoding="utf-8")
    for rel in ("001-Sample.md", base.INDEX):
        assert f"pre-image at upgrade-backups/1.0-to-1.1/backlog/{rel}" in rows, rel


def test_resplit_rows_name_the_real_backup_path(tmp_path):
    cfg, _backlog = _over_budget(tmp_path)
    assert base._migrate(cfg).state == "changelog_split"
    rows = (base._pair(cfg) / "DISPOSITIONS.md").read_text(encoding="utf-8")
    assert f"rewritten; pre-image at upgrade-backups/1.0-to-1.1/backlog/{CHANGELOG}" in rows


# --- abbreviations the config does not define ---

def test_unconfigured_abbrev_is_added_to_config_with_backup(tmp_path, capsys):
    cfg, backlog = base._project(tmp_path)
    config_path = backlog.parent / "config.yaml"
    original = base.CONFIG.replace("  INFRA: Infrastructure and DevOps\n", "").replace(
        "abbreviations:\n", "abbreviations:\n  # keep this comment\n") + "other_key: 1\n"
    base._write(config_path, original)
    report = base._migrate(cfg)
    assert report.state == "migrated", report.detail
    text = config_path.read_bytes().decode("utf-8")
    added = 'INFRA: "INFRA (added by the upgrade; edit the description)"'
    assert text == original.replace("  SMP: Sample work\n", f"  SMP: Sample work\n  {added}\n")
    assert "abbrev: INFRA" in (backlog / "ITEM-003-INFRA-Third.md").read_text(encoding="utf-8")
    # The pre-edit config is backed up byte-exact, and a DISPOSITIONS row names the addition and the backup.
    backed = [p for p in (base._pair(cfg) / "backlog").rglob("config.yaml")]
    assert [p.read_bytes() for p in backed] == [original.encode("utf-8")]
    rows = (base._pair(cfg) / "DISPOSITIONS.md").read_text(encoding="utf-8")
    assert "added INFRA under abbreviations:; pre-image at upgrade-backups/1.0-to-1.1/backlog/_outside/" in rows
    assert json.loads(mig.read_text(report.ledger_path))["abbreviations"] == {"added": ["INFRA"], "matched": []}
    bm._emit_backlog_migration_banner(report)
    assert "    abbreviations added:    INFRA" in capsys.readouterr().out


def test_case_insensitive_abbrev_matches_a_configured_key(tmp_path, capsys):
    index = base.legacy_index().replace("| NOT_STARTED | SMP | [001]", "| NOT_STARTED | smp | [001]")
    cfg, backlog = base._project(tmp_path, index)
    config_path = backlog.parent / "config.yaml"
    before = config_path.read_bytes()
    report = base._migrate(cfg)
    assert report.state == "migrated", report.detail
    assert config_path.read_bytes() == before  # a case match adds nothing to the config
    assert "abbrev: SMP" in (backlog / "001-Sample.md").read_text(encoding="utf-8")
    log = json.loads(mig.read_text(report.ledger_path))
    assert log["abbreviations"] == {"added": [], "matched": [{"from": "smp", "to": "SMP"}]}
    [cell] = [c for c in log["reconcile"]["cells"] if c["key"] == "abbrev"]
    assert (cell["index"], cell["winner"], cell["written"]) == ("smp", "configured-key", "SMP")
    bm._emit_backlog_migration_banner(report)
    assert "    abbreviations matched:  smp -> SMP" in capsys.readouterr().out
