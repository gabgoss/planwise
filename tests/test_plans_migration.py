#!/usr/bin/env python3
"""Tests for `plans_migration.py`: the routine `/planwise upgrade` and
`/planwise init` call around the plans-index migrator, and its banner.

One test per report state, plus the backup, DISPOSITIONS and banner cases.
Fixtures are the byte-built projects of `test_migrate_plans_index.py`. Nothing
here reads or writes the live project.

Run with:  python -m pytest tests/test_plans_migration.py -q
"""

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import config_loader
import generate_plans_index as gen
import migrate_plans_index as mig
import plans_migration as pm
import upgrade_io
from config_gen import InitConfig
from test_migrate_plans_index import (
    DATE,
    build,
    fixture_a,
    fixture_b,
    fixture_c,
    fixture_d,
    fixture_e,
    legacy_index,
)


@pytest.fixture(autouse=True)
def pin_today(monkeypatch):
    monkeypatch.setattr(mig, "_today", lambda: DATE)


def cfg_of(tmp_path):
    return InitConfig(project_name="t", project_root=tmp_path / "proj", plugin_root=SCRIPTS.parent)


def plans_tree(tmp_path):
    root = tmp_path / "proj" / "planwise" / "Plans"
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def pair_dir(tmp_path, pair="1.0-to-1.1"):
    return tmp_path / "proj" / "planwise" / "upgrade-backups" / pair


def migrate(tmp_path, versions=("1.0", "1.1"), **kwargs):
    return pm.migrate_plans_if_legacy(cfg_of(tmp_path), *versions, **kwargs)


def disposition_rows(tmp_path, action="plans-backed-up"):
    log = pair_dir(tmp_path) / "DISPOSITIONS.md"
    return [ln for ln in log.read_text(encoding="utf-8").splitlines() if f"{action}:" in ln] if log.exists() else []


# ---------------------------------------------------------------------------
# The nine report states: absent, generated, unrecognized, refused,
# backup_failed, write_failed, migrated, changelog_split, error. The plans
# index has no changelog, so `changelog_split` is in the vocabulary only.
# ---------------------------------------------------------------------------


def test_the_vocabulary_is_the_nine_shared_states_and_two_are_silent():
    assert pm.STATES == ("absent", "generated", "unrecognized", "refused", "backup_failed", "write_failed",
                         "migrated", "changelog_split", "error")
    assert pm.SILENT_STATES == ("absent", "generated")


def test_missing_config_missing_index_and_blank_index_are_absent(tmp_path):
    (tmp_path / "proj").mkdir()
    assert migrate(tmp_path).state == "absent"
    build(tmp_path, None, {})
    assert migrate(tmp_path).state == "absent"
    (tmp_path / "proj" / "planwise" / "Plans" / "00-Index-Plans.md").write_bytes(b" \r\n")
    assert migrate(tmp_path).state == "absent"
    assert not (tmp_path / "proj" / "planwise" / "upgrade-backups").exists()


def test_a_generated_index_is_silent_and_writes_nothing(tmp_path, capsys):
    fixture_d(tmp_path)
    before = plans_tree(tmp_path)
    report = migrate(tmp_path)
    assert report.state == "generated" and "--check exit 0" in report.detail
    pm._emit_plans_migration_banner(report)
    assert capsys.readouterr().out == ""
    assert plans_tree(tmp_path) == before and not (tmp_path / "proj" / "planwise" / "upgrade-backups").exists()


def test_an_unrecognized_index_is_reported_and_untouched(tmp_path):
    fixture_e(tmp_path)
    before = plans_tree(tmp_path)
    report = migrate(tmp_path)
    assert report.state == "unrecognized"
    assert report.fix.endswith("--report") and "migrate_plans_index.py --config" in report.fix
    assert plans_tree(tmp_path) == before


def test_a_plan_time_refusal_is_reported_untouched(tmp_path, monkeypatch):
    fixture_a(tmp_path)
    before = plans_tree(tmp_path)
    monkeypatch.setattr(gen, "HUB_TOKEN_BUDGET", 10)
    report = migrate(tmp_path)
    assert report.state == "refused" and "budget" in report.detail and "re-run /planwise upgrade" in report.fix
    assert plans_tree(tmp_path) == before and not pair_dir(tmp_path).exists()


def test_backup_failed_makes_zero_writes(tmp_path, monkeypatch):
    fixture_a(tmp_path)
    before = plans_tree(tmp_path)

    def refuse_copy(_src, _dst):
        raise OSError("simulated full disk")

    monkeypatch.setattr(upgrade_io, "_copy_bytes_exact", refuse_copy)
    report = migrate(tmp_path)
    assert report.state == "backup_failed" and "simulated full disk" in report.detail
    assert plans_tree(tmp_path) == before and disposition_rows(tmp_path) == []


def test_one_failing_copy_out_of_several_still_writes_nothing(tmp_path, monkeypatch):
    fixture_a(tmp_path)
    before = plans_tree(tmp_path)
    real = upgrade_io._copy_bytes_exact
    calls = []

    def fail_second(src, dst):
        calls.append(src)
        if len(calls) == 2:
            raise OSError("simulated failure on the second copy")
        real(src, dst)

    monkeypatch.setattr(upgrade_io, "_copy_bytes_exact", fail_second)
    assert migrate(tmp_path).state == "backup_failed"
    assert plans_tree(tmp_path) == before and disposition_rows(tmp_path) == []


def test_write_failed_restores_every_file_and_keeps_the_backup_rows(tmp_path, monkeypatch):
    fixture_a(tmp_path)
    before = plans_tree(tmp_path)
    monkeypatch.setattr(mig, "execute", lambda *args: print("FAIL: simulated") or 1)
    report = migrate(tmp_path)
    assert report.state == "write_failed" and "FAIL: simulated" in report.detail and report.backed_up
    assert plans_tree(tmp_path) == before
    assert len(disposition_rows(tmp_path)) == 3


def test_a_generator_failure_after_the_appends_restores_the_whole_tree(tmp_path, monkeypatch):
    fixture_a(tmp_path)
    before = plans_tree(tmp_path)

    def crash(*_a, **_k):
        raise RuntimeError("generator crashed")

    monkeypatch.setattr(gen, "write_plans_index", crash)
    report = migrate(tmp_path)
    assert report.state == "write_failed" and "restored" in report.detail
    assert plans_tree(tmp_path) == before


def test_a_second_attempt_after_write_failed_keeps_the_first_pre_images(tmp_path, monkeypatch):
    fixture_a(tmp_path)
    with monkeypatch.context() as patched:
        patched.setattr(mig, "execute", lambda *args: 1)
        assert migrate(tmp_path).state == "write_failed"
    report = migrate(tmp_path)
    assert report.state == "migrated" and len(report.kept) == 3 and report.diverged == {}


def test_legacy_index_migrates_with_byte_exact_backups_and_one_row_per_file(tmp_path):
    _config, plans_dir, index = fixture_a(tmp_path)
    before = plans_tree(tmp_path)
    report = migrate(tmp_path)
    assert report.state == "migrated", report.detail
    backups = pair_dir(tmp_path) / "plans"
    files = {p.relative_to(backups).as_posix(): p.read_bytes() for p in backups.rglob("*") if p.is_file()}
    assert files == {k: before[k] for k in ("00-Index-Plans.md", "Beta/BET-Master-Plan.md", "Gamma/GAM-Master-Plan.md")}
    assert len(disposition_rows(tmp_path)) == len(files) == 3
    assert report.ledger_path == plans_dir / mig.LEDGER_FILENAME and not report.git_dirty
    assert report.counts["appended"] == 2 and report.counts["master_plans"] == 2
    assert report.counts["status_changes"] == 1 and report.counts["unattributed"] == 0
    assert report.counts["generator_check_clean"] is True
    assert mig.classify_shape(index.read_text(encoding="utf-8"))[0] == "generated"


def test_the_init_pair_names_its_own_backup_folder(tmp_path):
    fixture_a(tmp_path)
    assert migrate(tmp_path, ("init", "1.1")).state == "migrated"
    assert (pair_dir(tmp_path, "init-to-1.1") / "plans" / "00-Index-Plans.md").is_file()


def test_the_reconcile_keyword_is_accepted_and_ignored(tmp_path):
    fixture_a(tmp_path / "a")
    fixture_a(tmp_path / "b")
    plain = migrate(tmp_path / "a")
    ignored = migrate(tmp_path / "b", reconcile="frontmatter-wins")
    assert plain.state == ignored.state == "migrated" and plain.counts == ignored.counts
    trees = [plans_tree(tmp_path / name) for name in ("a", "b")]
    for tree in trees:
        tree.pop(mig.LEDGER_FILENAME)  # the ledger names each project's own backup folder
    assert trees[0] == trees[1]


def test_second_call_after_migrated_is_generated_and_touches_nothing(tmp_path):
    fixture_a(tmp_path)
    assert migrate(tmp_path).state == "migrated"
    tree = plans_tree(tmp_path)
    backups = sorted(p for p in (tmp_path / "proj" / "planwise" / "upgrade-backups").rglob("*") if p.is_file())
    assert migrate(tmp_path).state == "generated"
    assert plans_tree(tmp_path) == tree
    assert sorted(p for p in (tmp_path / "proj" / "planwise" / "upgrade-backups").rglob("*") if p.is_file()) == backups


def test_every_migratable_fixture_reaches_migrated_and_never_changelog_split(tmp_path):
    states = set()
    for name, make in (("a", fixture_a), ("b", fixture_b), ("c", fixture_c), ("d", fixture_d), ("e", fixture_e)):
        make(tmp_path / name)
        states.add(migrate(tmp_path / name).state)
    assert states == {"migrated", "generated", "unrecognized"} and "changelog_split" not in states


def test_unexpected_exception_becomes_state_error(tmp_path, monkeypatch):
    fixture_a(tmp_path)

    def boom(*_a, **_k):
        raise RuntimeError("wild failure")

    monkeypatch.setattr(mig, "plan_migration", boom)
    report = migrate(tmp_path)
    assert report.state == "error" and "wild failure" in report.detail


def test_the_routine_never_raises_even_when_config_loading_does(tmp_path, monkeypatch):
    fixture_a(tmp_path)

    def boom(*_a, **_k):
        raise KeyError("no config")

    monkeypatch.setattr(config_loader, "load_config", boom)
    assert migrate(tmp_path).state == "error"


def test_a_legacy_seed_with_no_master_plans_is_migrated_not_unrecognized(tmp_path):
    build(tmp_path, legacy_index([]), {})
    assert migrate(tmp_path).state == "migrated"


def test_an_unclosed_comment_is_refused_with_zero_writes(tmp_path):
    row = "| ALP | Alpha | COMPLETE | 2026-01-10 | 2026-01-20 | Alpha/ |"
    build(tmp_path, legacy_index([row, "<!-- never closed"]), {})
    before = plans_tree(tmp_path)
    report = migrate(tmp_path)
    assert report.state == "refused" and "close the comment" in report.detail
    assert plans_tree(tmp_path) == before and not pair_dir(tmp_path).exists()


def _crash(*_a, **_k):
    raise RuntimeError("generator crashed")


def test_a_pre_existing_ledger_is_restored_on_write_failed(tmp_path, monkeypatch):
    _config, plans_dir, _index = fixture_a(tmp_path)
    old = b"# Plans Migration Ledger\r\n\r\nAn earlier migration's record.\r\n"
    (plans_dir / mig.LEDGER_FILENAME).write_bytes(old)
    before = plans_tree(tmp_path)
    monkeypatch.setattr(gen, "write_plans_index", _crash)
    report = migrate(tmp_path)
    assert report.state == "write_failed", report.detail
    assert (plans_dir / mig.LEDGER_FILENAME).read_bytes() == old
    assert plans_tree(tmp_path) == before


def test_the_routine_never_walks_the_whole_plans_tree(tmp_path, monkeypatch):
    fixture_a(tmp_path)

    def no_walk(*_a, **_k):
        raise AssertionError("the routine walked the whole plans tree")

    with monkeypatch.context() as patched:
        patched.setattr(Path, "rglob", no_walk)
        report = migrate(tmp_path)
    assert report.state == "migrated", report.detail


def test_the_readme_states_the_upgrade_path_backs_up_rather_than_refusing_a_dirty_master_plan():
    readme = (SCRIPTS.parent / "README.md").read_text(encoding="utf-8")
    assert "when a Master Plan it appends to has uncommitted changes" not in readme
    assert "backs up every Master Plan it appends to byte-exact before the append" in readme
    assert "`migrate_plans_index.py --write` refuses" in readme


def test_git_state_is_information_only_and_unknown_outside_a_repository(tmp_path):
    """The routine takes the plan with every write enabled; the git state is information only."""
    fixture_a(tmp_path)
    assert migrate(tmp_path).git_dirty is None


# ---------------------------------------------------------------------------
# The banner
# ---------------------------------------------------------------------------


def _report(state, **kwargs):
    index = Path("planwise/Plans/00-Index-Plans.md")
    return pm.PlansMigrationReport(state=state, index_path=index, backup_dir=Path("b"), **kwargs)


@pytest.mark.parametrize(
    "state,headline",
    [
        ("refused", "Plans index migration: REFUSED (index and Master Plans left untouched)"),
        ("unrecognized", "is not a hand-authored or generated index -- left untouched"),
        ("backup_failed", "Plans index migration: BACKUP FAILED -- no write was attempted"),
        ("write_failed", "Plans index migration: WRITE FAILED"),
        ("error", "Plans index migration: ERROR (nothing else in this run depends on it)"),
    ],
)
def test_banner_names_each_state(capsys, state, headline):
    pm._emit_plans_migration_banner(_report(state, detail="why", fix="do this"))
    out = capsys.readouterr().out
    assert headline in out and out.startswith("Plans index migration:")


@pytest.mark.parametrize("state", ["absent", "generated"])
def test_banner_is_silent_when_nothing_happened(capsys, state):
    pm._emit_plans_migration_banner(_report(state))
    assert capsys.readouterr().out == ""


def test_the_migrated_banner_counts_and_names_the_ledger_and_the_backups(tmp_path, capsys):
    fixture_c(tmp_path)
    report = migrate(tmp_path)
    assert report.state == "migrated", report.detail
    pm._emit_plans_migration_banner(report)
    out = capsys.readouterr().out
    lines = out.splitlines()
    assert lines[0] == "Plans index migration:"
    assert "index notes appended:    5 item(s) into 2 Master Plan(s), 0 already present" in out
    assert "unattributed notes:      3" in out and "status changes:" in out
    assert str(report.ledger_path) in out and str(report.backup_dir) in out
    assert "generator --check:" in out and "clean" in out


def test_the_migrated_banner_counts_status_changes(tmp_path, capsys):
    fixture_a(tmp_path)
    pm._emit_plans_migration_banner(migrate(tmp_path))
    assert "status changes:          1" in capsys.readouterr().out


def test_banner_never_raises_on_a_malformed_report(capsys):
    pm._emit_plans_migration_banner(pm.PlansMigrationReport(state="migrated", index_path=None, counts=None))
    assert capsys.readouterr().out.startswith("Plans index migration:")

