#!/usr/bin/env python3
"""Tests for `plans_migration.py`: the routine `/planwise upgrade` and
`/planwise init` call around the plans-index migrator, and its banner.

One test per report state, plus the backup, DISPOSITIONS and banner cases.
Fixtures are the byte-built projects of `test_migrate_plans_index.py`. Nothing
here reads or writes the live project.

Run with:  python -m pytest tests/test_plans_migration.py -q
"""

import os
import shutil
import subprocess
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
    A_PLANS,
    DATE,
    build,
    fixture_a,
    fixture_b,
    fixture_c,
    fixture_d,
    fixture_e,
    legacy_index,
    master_plan,
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
# The ten report states: absent, generated, unrecognized, deferred, refused,
# backup_failed, write_failed, migrated, changelog_split, error. The plans
# index has no changelog, so `changelog_split` is in the vocabulary only.
# ---------------------------------------------------------------------------


def test_the_vocabulary_is_the_ten_shared_states_and_two_are_silent():
    assert pm.STATES == ("absent", "generated", "unrecognized", "deferred", "refused", "backup_failed",
                         "write_failed", "migrated", "changelog_split", "error")
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


def test_generated_index_with_unknown_status_prints_the_anomaly(tmp_path, capsys):
    plans = dict(A_PLANS)
    raw = "NEEDS_REDESIGN — trailing prose"
    plans["Beta/BET-Master-Plan.md"] = master_plan("Beta", raw, "2026-02-01", "2026-02-10")
    config, _plans_dir, _index = build(tmp_path, None, plans)
    assert gen.write_plans_index(config).exit_code == 1  # the write keeps the anomaly and still writes the index
    before = plans_tree(tmp_path)
    report = migrate(tmp_path)
    assert report.state == "generated" and "--check exit 1" in report.detail
    assert [a["class"] for a in report.anomalies] == ["unknown-status"]
    pm._emit_plans_migration_banner(report)
    out = capsys.readouterr().out
    assert "Plans index: generated; --check reports 1 anomaly(ies)" in out
    assert "  unknown-status: Beta/BET-Master-Plan.md" in out
    assert f"    Status line: {raw}" in out
    assert "    reduced to:  NEEDS_REDESIGN  (not in plan_statuses)" in out
    assert f'  fix: python "{SCRIPTS / pm.WRITER}" --config "' in out and "flip_plan_status.py" in out
    assert plans_tree(tmp_path) == before and not (tmp_path / "proj" / "planwise" / "upgrade-backups").exists()


def _banner_map_line(out, anomaly_file):
    """The `map line:` the banner prints under the anomaly for `anomaly_file`."""
    lines = out.splitlines()
    block = lines[lines.index(next(ln for ln in lines if ln.endswith(f": {anomaly_file}"))) + 1:]
    shown = next(ln for ln in block if ln.strip().startswith("map line:"))
    return shown.split("map line:", 1)[1].strip()


def _run_writer(tmp_path, map_text):
    """Run the real `flip_plan_status.main()` on the fixture project with a map built from banner text."""
    import flip_plan_status

    config_path = tmp_path / "proj" / "planwise" / "config.yaml"
    map_file = tmp_path / "map.txt"
    map_file.write_text(map_text, encoding="utf-8")
    old_argv = sys.argv
    sys.argv = ["flip_plan_status.py", "--config", str(config_path), str(map_file)]
    try:
        return flip_plan_status.main()
    finally:
        sys.argv = old_argv


@pytest.mark.parametrize("rel", ["Beta/BET-Master-Plan.md", "Alpha/Exec-ALP/ALP-Master-Plan.md"],
                         ids=["top-level", "nested-exec"])
def test_the_banner_map_line_is_accepted_by_the_real_writer(tmp_path, capsys, rel):
    plans = dict(A_PLANS)
    plans[rel] = master_plan("Plan", "NEEDS_REDESIGN — trailing prose", "2026-02-01", "2026-02-10")
    config, _plans_dir, _index = build(tmp_path, None, plans)
    assert gen.write_plans_index(config).exit_code == 1
    report = migrate(tmp_path)
    assert [a["file"] for a in report.anomalies] == [rel]
    pm._emit_plans_migration_banner(report)
    out = capsys.readouterr().out
    shown = _banner_map_line(out, rel)
    assert "{Path}" not in shown and shown.endswith(": {STATUS}")
    assert _run_writer(tmp_path, shown.replace("{STATUS}", "COMPLETE") + "\n") == 0  # not REFUSED
    flipped = (tmp_path / "proj" / "planwise" / "Plans" / rel).read_text(encoding="utf-8")
    assert "**Status:** COMPLETE — trailing prose" in flipped


def test_missing_status_gets_a_hand_fix_hint_and_no_writer_command(tmp_path, capsys):
    plans = dict(A_PLANS)
    plans["Beta/BET-Master-Plan.md"] = b"# Beta Master Plan\n\n**Created:** 2026-02-01\n\nBody.\n\n*Last Updated: 2026-02-10*\n"
    config, _plans_dir, _index = build(tmp_path, None, plans)
    assert gen.write_plans_index(config).exit_code == 1
    report = migrate(tmp_path)
    assert [a["class"] for a in report.anomalies] == ["missing-status"] and report.fix == ""
    pm._emit_plans_migration_banner(report)
    out = capsys.readouterr().out
    assert "  missing-status: Beta/BET-Master-Plan.md" in out
    assert "    hand-fix:    add a **Status:** line to that Master Plan" in out
    assert "  fix: " not in out and 'python "' not in out and "map line:" not in out


def test_unknown_plus_missing_prints_one_writer_command_and_a_map_line_only_for_the_unknown(tmp_path, capsys):
    plans = dict(A_PLANS)
    plans["Beta/BET-Master-Plan.md"] = master_plan("Beta", "NEEDS_REDESIGN — x", "2026-02-01", "2026-02-10")
    plans["Gamma/GAM-Master-Plan.md"] = b"# Gamma Master Plan\n\n**Created:** 2026-03-01\n\nBody.\n"
    config, _plans_dir, _index = build(tmp_path, None, plans)
    gen.write_plans_index(config)
    report = migrate(tmp_path)
    assert sorted(a["class"] for a in report.anomalies) == ["missing-status", "unknown-status"]
    pm._emit_plans_migration_banner(report)
    out = capsys.readouterr().out
    assert out.count("  fix: python ") == 1 and out.count("map line:") == 1
    assert "    map line:    Beta/: {STATUS}" in out


@pytest.mark.parametrize("raw", ["In Progress", "Not started"], ids=["in-progress", "not-started"])
def test_a_multi_word_status_gets_a_hand_fix_naming_the_refusal_and_no_writer_line(tmp_path, capsys, raw):
    import flip_plan_status

    plans = dict(A_PLANS)
    plans["Beta/BET-Master-Plan.md"] = master_plan("Beta", raw, "2026-02-01", "2026-02-10")
    config, _plans_dir, _index = build(tmp_path, None, plans)
    gen.write_plans_index(config)
    report = migrate(tmp_path)
    assert [a["class"] for a in report.anomalies] == ["unknown-status"] and report.fix == ""
    reason = flip_plan_status.status_value_refusal(raw)  # the writer's own verdict is the source
    assert reason
    pm._emit_plans_migration_banner(report)
    out = capsys.readouterr().out
    assert "  unknown-status: Beta/BET-Master-Plan.md" in out
    assert "map line:" not in out and "  fix: " not in out and 'python "' not in out
    hand = next(ln for ln in out.splitlines() if ln.strip().startswith("hand-fix:"))
    assert pm.WRITER in hand and reason.removesuffix(" -- edit by hand") in hand


def test_one_flippable_and_one_multi_word_status_print_one_map_line_and_one_writer_command(tmp_path, capsys):
    plans = dict(A_PLANS)
    plans["Beta/BET-Master-Plan.md"] = master_plan("Beta", "NEEDS_REDESIGN — x", "2026-02-01", "2026-02-10")
    plans["Gamma/GAM-Master-Plan.md"] = master_plan("Gamma", "In Progress", "2026-03-01", "2026-03-10")
    config, _plans_dir, _index = build(tmp_path, None, plans)
    gen.write_plans_index(config)
    report = migrate(tmp_path)
    assert [a["class"] for a in report.anomalies] == ["unknown-status", "unknown-status"]
    pm._emit_plans_migration_banner(report)
    out = capsys.readouterr().out
    assert out.count("map line:") == 1 and "    map line:    Beta/: {STATUS}" in out
    assert out.count("  fix: python ") == 1 and out.count("hand-fix:") == 1


def _link_plan_folder(tmp_path, name):
    """Move `Plans/{name}` aside and put a directory link (a symlink, else a Windows junction) in its place."""
    plans = tmp_path / "proj" / "planwise" / "Plans"
    real = tmp_path / "elsewhere" / name
    real.parent.mkdir(exist_ok=True)
    shutil.move(str(plans / name), str(real))
    link = plans / name
    try:
        link.symlink_to(real, target_is_directory=True)
    except (OSError, NotImplementedError):  # no symlink right: a Windows junction needs none
        made = (subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(real)], capture_output=True, check=False)
                if os.name == "nt" else None)
        if made is None or made.returncode != 0:
            pytest.skip("neither a symlink nor a junction can be made here")
    return real


def _writer_hand_fix_lines(out):
    return [ln for ln in out.splitlines() if ln.strip().startswith("hand-fix:")]


def test_two_master_plans_on_one_path_get_a_hand_fix_and_no_map_line_the_writer_would_refuse(tmp_path, capsys):
    plans = dict(A_PLANS)
    plans["Beta/BET-Master-Plan.md"] = master_plan("Beta", "NEEDS_REDESIGN — x", "2026-02-01", "2026-02-10")
    plans["Beta/BTB-Master-Plan.md"] = master_plan("Beta", "NEEDS_REDESIGN — y", "2026-02-01", "2026-02-10")
    config, _plans_dir, _index = build(tmp_path, None, plans)
    gen.write_plans_index(config)
    report = migrate(tmp_path)
    unknown = [a for a in report.anomalies if a["class"] == "unknown-status"]
    assert len(unknown) == 2  # the generator also reports the shared Path as its own anomaly
    pm._emit_plans_migration_banner(report)
    out = capsys.readouterr().out
    assert "map line:" not in out and "  fix: " not in out and report.fix == ""
    hands = _writer_hand_fix_lines(out)
    assert len(hands) == 2 and all("2 Master Plans" in ln for ln in hands)
    assert _run_writer(tmp_path, "Beta/: COMPLETE\n") == 1  # the writer does refuse that Path


def test_a_linked_plan_folder_gets_a_hand_fix_and_no_map_line_the_writer_would_refuse(tmp_path, capsys):
    plans = dict(A_PLANS)
    plans["Beta/BET-Master-Plan.md"] = master_plan("Beta", "NEEDS_REDESIGN — x", "2026-02-01", "2026-02-10")
    config, _plans_dir, _index = build(tmp_path, None, plans)
    real = _link_plan_folder(tmp_path, "Beta")
    gen.write_plans_index(config)
    before = (real / "BET-Master-Plan.md").read_bytes()
    report = migrate(tmp_path)
    assert [a["file"] for a in report.anomalies] == ["Beta/BET-Master-Plan.md"]
    pm._emit_plans_migration_banner(report)
    out = capsys.readouterr().out
    assert "map line:" not in out and "  fix: " not in out and report.fix == ""
    assert any("symlink or junction" in ln for ln in _writer_hand_fix_lines(out))
    assert _run_writer(tmp_path, "Beta/: COMPLETE\n") == 1
    assert (real / "BET-Master-Plan.md").read_bytes() == before


def test_a_plans_dir_less_report_keeps_the_value_check_alone():
    found = {"class": "unknown-status", "file": "Beta/BET-Master-Plan.md", "raw": "NEEDS_REDESIGN — x"}
    assert pm._writer_refusal(found) is None
    assert pm._writer_refusal(dict(found, raw="In Progress")) is not None


def test_generated_index_clean_stays_silent(tmp_path, capsys):
    fixture_d(tmp_path)
    report = migrate(tmp_path)
    assert report.state == "generated" and report.anomalies == [] and report.fix == ""
    pm._emit_plans_migration_banner(report)
    assert capsys.readouterr().out == ""


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
    assert report.state == "refused" and "budget" in report.detail and "then re-run" in report.detail
    assert report.fix == "close each refusal listed above as its text says"
    assert plans_tree(tmp_path) == before and not pair_dir(tmp_path).exists()


def test_an_unaccounted_bytes_refusal_tells_the_user_to_keep_the_index_and_not_to_rerun(tmp_path, monkeypatch):
    fixture_a(tmp_path)
    before = plans_tree(tmp_path)
    monkeypatch.setattr(mig, "accounting", lambda _plan: {"unaccounted": 7})
    report = migrate(tmp_path)
    assert report.state == "refused" and "migrator defect" in report.detail
    assert report.fix == mig.UNACCOUNTED_FIX and "re-run" not in report.fix
    assert plans_tree(tmp_path) == before


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


def test_an_unclosed_comment_migrates_with_backups(tmp_path):
    row = "| ALP | Alpha | COMPLETE | 2026-01-10 | 2026-01-20 | Alpha/ |"
    build(tmp_path, legacy_index([row, "<!-- never closed"]), {})
    report = migrate(tmp_path)
    assert report.state == "migrated", report.detail
    assert pair_dir(tmp_path).exists()


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


def test_unrecognized_banner_prints_detail_not_a_command(tmp_path, capsys):
    fixture_e(tmp_path)
    report = migrate(tmp_path)
    assert report.state == "unrecognized" and report.detail
    pm._emit_plans_migration_banner(report)
    out = capsys.readouterr().out
    assert "detail:" in out and "inspect it with" not in out


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


@pytest.mark.parametrize("verdict,token", [
    ("clean", "clean"),
    ("accepted", "clean apart from tree anomalies"),
    ("dirty", "not clean"),
])
def test_the_generator_check_token_states_the_verdict_and_gives_no_instruction(verdict, token):
    report = _report("migrated", counts={"generator_verdict": verdict}, git_dirty=False)
    [line] = [ln for ln in pm._migrated_lines(report) if "generator --check" in ln]
    assert line.endswith(token) and "re-run" not in line


def test_the_migrated_banner_counts_status_changes(tmp_path, capsys):
    fixture_a(tmp_path)
    pm._emit_plans_migration_banner(migrate(tmp_path))
    assert "status changes:          1" in capsys.readouterr().out


def test_banner_never_raises_on_a_malformed_report(capsys):
    pm._emit_plans_migration_banner(pm.PlansMigrationReport(state="migrated", index_path=None, counts=None))
    assert capsys.readouterr().out.startswith("Plans index migration:")

