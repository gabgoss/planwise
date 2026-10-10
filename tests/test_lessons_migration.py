"""Tests for lessons_migration.py: the upgrade/init orchestrator around the
lessons index migrator. One test per report state, plus the DISPOSITIONS
row, backup byte-equality, and banner cases. Fixtures live under tmp_path,
never under plugins/planwise/, and are written as bytes."""
import re
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import lessons_bootstrap
import lessons_migration as lm
import migrate_lessons_index as mig
import migrate_lessons_support as sup
import upgrade_io
from config_gen import InitConfig

CONFIG_YAML = (
    'project:\n  name: "test-project"\n  lessons_dir: "LessonsLearned"\n  index_files:\n'
    '    lessons: "00-Index-LessonsLearned.md"\n'
    'lesson_statuses:\n- documented\n- promoted\n- applied\n- rule\n- orphaned\n'
)
MASTER_HEADER = "| ID | Title | Category | Severity | Language | Technology | Domain | Source | Status |\n"
MASTER_SEP = "|----|----|----|----|----|----|----|----|----|\n"
LESSON_001 = (
    "---\nid: LL-001\ntitle: Fixture Lesson One\ncategory: process\nseverity: medium\n"
    "language: [python]\ntechnology: [claude-code]\ndomain: [PROC]\nsource: fixture\n"
    "status: documented\n---\n\n# LL-001-PROC: Fixture Lesson One\n\n## Context\n\nSomething happened.\n"
)
LEGACY_INDEX = (
    "# Lessons Learned Index\n\n**Last Updated:** 2024-01-01\n\n**Next available ID:** LL-002\n\n---\n\n"
    "## Master Table\n\n" + MASTER_HEADER + MASTER_SEP +
    "| LL-001 | Fixture Lesson One | process | medium | python | claude-code | PROC | fixture | documented |\n"
    "\n---\n"
)
GENERATED_INDEX = (
    "Generated: 2024-01-01\n**Next available ID:** LL-002\n\n"
    "| ID | Title | Category | Severity | Language | Technology | Domain | Source | Status | File |\n"
    "|----|----|----|----|----|----|----|----|----|----|\n"
    "| LL-001 | Fixture Lesson One | process | medium | python | claude-code | PROC | fixture | documented | "
    "[001](LL-001-PROC-One.md) |\n"
)
UNRECOGNIZED_INDEX = "# Some Other Document\n\nJust prose, no table, no heading.\n"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def _project(tmp_path, index_text=None):
    root = tmp_path / "proj"
    lessons_dir = root / "planwise" / "LessonsLearned"
    _write(root / "planwise" / "config.yaml", CONFIG_YAML)
    (lessons_dir / "Archive").mkdir(parents=True, exist_ok=True)
    _write(lessons_dir / "00-Index-LessonsLearned.md", LEGACY_INDEX if index_text is None else index_text)
    _write(lessons_dir / "LL-001-PROC-One.md", LESSON_001)
    cfg = InitConfig(project_name="test-project", project_root=root, plugin_root=SCRIPTS.parent)
    return cfg, lessons_dir


def _snapshot(root: Path) -> dict:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*")
            if p.is_file() and ".git" not in p.parts}


def _pair(cfg, pair="1.0-to-1.1") -> Path:
    return cfg.project_root / "planwise" / "upgrade-backups" / pair


def _migrate(cfg, versions=("1.0", "1.1")):
    return lm.migrate_lessons_if_legacy(cfg, *versions)


# ---------------------------------------------------------------------------
# The nine report states: absent, generated, unrecognized, refused,
# backup_failed, write_failed, migrated, changelog_split, error.
# `changelog_split` reaches on the `generated` branch when
# `lessons_changelog.plan_split` finds the changelog over budget -- see the
# dedicated tests below (a project with no changelog file yet, and one
# whose changelog is within budget, both stay `generated`).
# ---------------------------------------------------------------------------


def test_missing_config_or_index_is_absent(tmp_path):
    root = tmp_path / "empty"
    root.mkdir()
    cfg = InitConfig(project_name="x", project_root=root, plugin_root=SCRIPTS.parent)
    assert _migrate(cfg).state == "absent"
    _write(root / "planwise" / "config.yaml", CONFIG_YAML)
    assert _migrate(cfg).state == "absent" and not (root / "planwise" / "upgrade-backups").exists()


def test_generated_shape_is_silent_and_checks_both(tmp_path, capsys):
    cfg, _lessons_dir = _project(tmp_path, GENERATED_INDEX)
    before = _snapshot(tmp_path)
    report = _migrate(cfg)
    lm._emit_lessons_migration_banner(report)
    assert report.state == "generated"
    assert "index --check exit" in report.detail and "companion --check exit" in report.detail
    assert capsys.readouterr().out == ""
    assert _snapshot(tmp_path) == before


def _seed_changelog(lessons_dir: Path, entries: list) -> None:
    """`entries`: `[(number, body), ...]`, newest first."""
    lines = ["[← 00-Index-LessonsLearned.md](00-Index-LessonsLearned.md)", ""]
    for n, body in entries:
        lines += [f"## Entry {n}", "", body, ""]
    _write(lessons_dir / "00-Changelog-LessonsLearned.md", "\n".join(lines) + "\n")


_FILLER = "Lorem ipsum filler text describing a fixture entry body in full. " * 90


def test_within_budget_changelog_stays_generated_and_writes_nothing(tmp_path, capsys):
    cfg, lessons_dir = _project(tmp_path, GENERATED_INDEX)
    _seed_changelog(lessons_dir, [(2, "Second."), (1, "First.")])
    before = _snapshot(tmp_path)
    report = _migrate(cfg)
    lm._emit_lessons_migration_banner(report)
    assert report.state == "generated"
    assert _snapshot(tmp_path) == before
    assert capsys.readouterr().out == ""


def test_over_budget_changelog_reaches_changelog_split_and_emits_banner(tmp_path, capsys):
    cfg, lessons_dir = _project(tmp_path, GENERATED_INDEX)
    _seed_changelog(lessons_dir, [(n, _FILLER) for n in range(30, 0, -1)])
    report = _migrate(cfg)
    assert report.state == "changelog_split"
    assert report.counts["changelog_parts"] >= 2
    assert any(p.name.startswith("00-Changelog-LessonsLearned-Archive-") for p in lessons_dir.glob("*.md"))
    main_text = (lessons_dir / "00-Changelog-LessonsLearned.md").read_text(encoding="utf-8")
    assert "Older entries:" in main_text
    lm._emit_lessons_migration_banner(report)
    out = capsys.readouterr().out
    assert f"Lessons changelog: re-split into {report.counts['changelog_parts']} part(s)" in out
    assert str(report.backup_dir) in out


def test_changelog_refusal_prints_its_own_fix(tmp_path, capsys):
    cfg, lessons_dir = _project(tmp_path, GENERATED_INDEX)
    _seed_changelog(lessons_dir, [(n, _FILLER) for n in range(30, 0, -1)])
    changelog = lessons_dir / "00-Changelog-LessonsLearned.md"
    text = changelog.read_text(encoding="utf-8")
    _write(changelog, text.replace("[← 00-Index-LessonsLearned.md](00-Index-LessonsLearned.md)", "not a backlink line", 1))
    report = _migrate(cfg)
    assert report.state == "refused"
    assert "expected a backlink line" in report.detail
    assert "restore the backlink line the generator writes" in report.fix
    assert "fix the changelog line named above" not in report.fix
    assert "hand-authored" not in report.fix
    lm._emit_lessons_migration_banner(report)
    out = capsys.readouterr().out
    assert "  fix:    restore the backlink line" in out


def test_changelog_refusal_keeps_a_keep_it_fix(tmp_path):
    report = lm.LessonsMigrationReport(state="generated", index_path=tmp_path / "x.md", backup_dir=None)
    lm._refuse_changelog(report, sup.Refusal("it would change", "keep the changelog as it is and report a defect"))
    assert report.detail == "it would change"
    assert report.fix.startswith("keep the changelog as it is and report a defect")
    assert "fix the changelog line named above" not in report.fix


def test_second_run_after_changelog_split_is_silent(tmp_path, capsys):
    cfg, lessons_dir = _project(tmp_path, GENERATED_INDEX)
    _seed_changelog(lessons_dir, [(n, _FILLER) for n in range(30, 0, -1)])
    first = _migrate(cfg)
    assert first.state == "changelog_split"
    before = _snapshot(tmp_path)
    second = _migrate(cfg)
    lm._emit_lessons_migration_banner(second)
    assert second.state == "generated"
    assert _snapshot(tmp_path) == before
    assert capsys.readouterr().out == ""


_BACKLINK = "[← 00-Index-LessonsLearned.md](00-Index-LessonsLearned.md)"
_MAIN = "00-Changelog-LessonsLearned.md"
_ARCHIVE = "00-Changelog-LessonsLearned-Archive-2026.md"
_PART_03 = "00-Changelog-LessonsLearned-Archive-2026-Part-03.md"


def _family_file(heads: list, entries: list, nl: str = "\n", pointer: bool = False) -> bytes:
    """One changelog family file by bytes; `entries` newest first: [(n, body)]."""
    text = "".join(f"{h}{nl}{nl}" for h in heads)
    text += "".join(f"## Entry {n}{nl}{nl}{b}{nl}{nl}" for n, b in entries)
    if pointer:
        text += f"Older entries: [{_ARCHIVE}]({_ARCHIVE}){nl}"
    return text.encode("utf-8")


def _marked(n: int) -> str:
    return f"{_FILLER}marker-{n:03d}."


def _failing_replace(fail_on: int):
    import os
    calls = {"n": 0}

    def fake(src, dst):
        calls["n"] += 1
        if calls["n"] == fail_on:
            raise PermissionError(13, "simulated: the file is locked", str(dst))
        os.replace(src, dst)
    return fake


def _seed_gap_family(lessons_dir: Path) -> bytes:
    """Main over budget, the archive, and an orphan -Part-03 after a missing
    -Part-02. Returns the orphan's bytes."""
    _write(lessons_dir / _MAIN, _family_file([_BACKLINK], [(n, _marked(n)) for n in range(40, 10, -1)],
                                             pointer=True).decode("utf-8"))
    _write(lessons_dir / _ARCHIVE, _family_file([f"[← {_MAIN}]({_MAIN})", _BACKLINK],
                                                [(n, _marked(n)) for n in range(10, 5, -1)]).decode("utf-8"))
    part3 = _family_file([f"[← {_ARCHIVE}]({_ARCHIVE})"], [(n, _marked(n)) for n in range(5, 0, -1)])
    (lessons_dir / _PART_03).write_bytes(part3)
    return part3


def test_orphan_part_after_a_gap_is_backed_up_kept_and_logged_honestly(tmp_path):
    cfg, lessons_dir = _project(tmp_path, GENERATED_INDEX)
    part3 = _seed_gap_family(lessons_dir)
    report = _migrate(cfg)
    assert report.state == "changelog_split", report.detail
    family = "".join(p.read_bytes().decode("utf-8") for p in lessons_dir.glob("00-Changelog-*.md"))
    for n in range(1, 41):
        assert family.count(f"marker-{n:03d}.") == 1, n
    assert (_pair(cfg) / "lessons" / _PART_03).read_bytes() == part3
    rows = [ln for ln in (_pair(cfg) / "DISPOSITIONS.md").read_text(encoding="utf-8").splitlines()
            if _PART_03 in ln]
    assert rows and all("created" not in ln for ln in rows), rows


def test_write_failure_never_deletes_a_file_that_existed_before_the_run(tmp_path, monkeypatch):
    import migrate_backlog_support
    cfg, lessons_dir = _project(tmp_path, GENERATED_INDEX)
    part3 = _seed_gap_family(lessons_dir)
    before = _snapshot(lessons_dir)
    monkeypatch.setattr(migrate_backlog_support, "_replace", _failing_replace(2))
    report = _migrate(cfg)
    assert report.state == "write_failed", report.detail
    assert (lessons_dir / _PART_03).read_bytes() == part3
    assert _snapshot(lessons_dir) == before


def test_single_oversized_entry_converges_silently_with_no_writes(tmp_path, capsys):
    cfg, lessons_dir = _project(tmp_path, GENERATED_INDEX)
    _write(lessons_dir / _MAIN, _family_file([_BACKLINK], [(3, "Small newest."), (2, "Small.")], pointer=True)
           .decode("utf-8"))
    _write(lessons_dir / _ARCHIVE, _family_file([f"[← {_MAIN}]({_MAIN})", _BACKLINK], [(1, "y" * 70_000)])
           .decode("utf-8"))
    before = _snapshot(tmp_path)
    for _run in range(2):
        report = _migrate(cfg)
        lm._emit_lessons_migration_banner(report)
        assert report.state == "generated", report.detail
        assert _snapshot(tmp_path) == before
    assert capsys.readouterr().out == ""
    config = lm.config_loader.load_config(Path(mig.__file__), config_path=cfg.project_root / "planwise" / "config.yaml")
    rep = mig.build_report(config, lessons_dir / "00-Index-LessonsLearned.md")
    assert rep["changelog_resplit"] == "converged"
    assert [(o["file"], o["entry"]) for o in rep["changelog_oversized"]] == [(_ARCHIVE, 1)]


def test_unstable_family_is_renumbered_once_then_silent(tmp_path, capsys):
    cfg, lessons_dir = _project(tmp_path, GENERATED_INDEX)
    # Positional scheme from an earlier migrator: newest is Entry 1, and the
    # archive restarts at 1; a later max + 1 entry (4) sits on top.
    _write(lessons_dir / _MAIN, _family_file([_BACKLINK], [(4, "d"), (1, "c"), (2, "b")], pointer=True)
           .decode("utf-8"))
    _write(lessons_dir / _ARCHIVE, _family_file([f"[← {_MAIN}]({_MAIN})", _BACKLINK], [(1, "a")])
           .decode("utf-8"))
    report = _migrate(cfg)
    assert report.state == "changelog_split", report.detail
    lm._emit_lessons_migration_banner(report)
    # (D) The archive's one entry (already numbered 1 by position) is left
    # byte-identical by the renumber, so only the main file is actually
    # written -- the banner's file count must say 1, not the family's 2.
    out = capsys.readouterr().out
    assert "Lessons changelog: renumbered 4 entries by position (the oldest is Entry 1) across 1 file(s)" in out
    assert (lessons_dir / _MAIN).read_bytes() == _family_file([_BACKLINK], [(4, "d"), (3, "c"), (2, "b")],
                                                              pointer=True)
    after = _snapshot(tmp_path)
    second = _migrate(cfg)
    assert second.state == "generated"
    assert _snapshot(tmp_path) == after


def test_changelog_split_banner_states_the_real_limits(capsys):
    report = lm.LessonsMigrationReport(state="changelog_split", index_path=None, backup_dir=Path("b"),
                                       counts={"changelog_parts": 3, "changelog_kind": "split",
                                               "changelog_renumbered": 0})
    lm._emit_lessons_migration_banner(report)
    line = capsys.readouterr().out.splitlines()[0]
    assert line.startswith("Lessons changelog: re-split into 3 part(s) (main file under 22000 tokens, "
                           "each archive part under 25000; a file holding one larger entry keeps it whole)")
    assert "each ≤" not in line


def test_unrecognized_shape_is_reported_and_untouched(tmp_path):
    cfg, _lessons_dir = _project(tmp_path, UNRECOGNIZED_INDEX)
    before = _snapshot(tmp_path)
    report = _migrate(cfg)
    assert report.state == "unrecognized"
    assert report.fix.endswith("--report") and "migrate_lessons_index.py --config" in report.fix
    assert _snapshot(tmp_path) == before


def test_refused_names_the_flag_it_closes(tmp_path):
    cfg, lessons_dir = _project(tmp_path)
    _write(lessons_dir / "LL-001-PROC-Dup.md", LESSON_001)  # LL-001 now resolves to two files
    before = _snapshot(tmp_path)
    report = _migrate(cfg)
    assert report.state == "refused"
    assert "resolves to 2 file" in report.detail and sup.FIX_RESOLVE in report.detail
    assert _snapshot(tmp_path) == before


def test_backup_failed_makes_zero_writes(tmp_path, monkeypatch):
    cfg, _lessons_dir = _project(tmp_path)
    before = _snapshot(tmp_path)

    def refuse_copy(_src, _dst):
        raise OSError("simulated full disk")
    monkeypatch.setattr(upgrade_io, "_copy_bytes_exact", refuse_copy)
    report = _migrate(cfg)
    assert report.state == "backup_failed" and "simulated full disk" in report.detail
    assert _snapshot(tmp_path) == before


def test_write_failed_is_reported_after_the_backup(tmp_path, monkeypatch):
    cfg, _lessons_dir = _project(tmp_path)
    monkeypatch.setattr(mig, "execute", lambda *args: print("FAIL: simulated") or 1)
    report = _migrate(cfg)
    assert report.state == "write_failed" and "FAIL: simulated" in report.detail
    assert report.backed_up


def test_legacy_index_migrates_with_byte_exact_backups(tmp_path):
    cfg, lessons_dir = _project(tmp_path)
    before_index = (lessons_dir / "00-Index-LessonsLearned.md").read_bytes()
    before_lesson = (lessons_dir / "LL-001-PROC-One.md").read_bytes()
    report = _migrate(cfg)
    assert report.state == "migrated", report.detail
    assert report.companion_regenerated is True
    backups = _pair(cfg) / "lessons"
    assert (backups / "00-Index-LessonsLearned.md").read_bytes() == before_index
    assert (backups / "LL-001-PROC-One.md").read_bytes() == before_lesson
    text = (lessons_dir / "00-Index-LessonsLearned.md").read_text(encoding="utf-8")
    assert sup.classify_shape(text)[0] == "generated"


LEGACY_INDEX_WITH_HISTORY = (
    "# Lessons Learned Index\n\n**Last Updated:** 2024-01-01 (history)\n\n"
    "<!-- Previous: 2023-12-01 - older -->\n\n**Next available ID:** LL-002\n\n---\n\n"
    "## Master Table\n\n" + MASTER_HEADER + MASTER_SEP +
    "| LL-001 | Fixture Lesson One | process | medium | python | claude-code | PROC | fixture | documented |\n"
    "\n---\n"
)


def test_verify_written_miss_prevents_state_migrated(tmp_path, monkeypatch):
    """A planned output (the changelog) that does not land as staged makes
    `mig.execute` return non-zero via `verify_written`'s miss -- and that
    failure surfaces as `write_failed`, never `migrated`."""
    cfg, lessons_dir = _project(tmp_path, LEGACY_INDEX_WITH_HISTORY)
    changelog_path = lessons_dir / "00-Changelog-LessonsLearned.md"
    real_replace_all = sup.replace_all

    def _corrupting_replace_all(staged):
        done = real_replace_all(staged)
        if changelog_path in done:
            changelog_path.write_bytes(b"corrupted after replace\n")
        return done

    monkeypatch.setattr(sup, "replace_all", _corrupting_replace_all)
    report = _migrate(cfg)
    assert report.state != "migrated"
    assert report.state == "write_failed"
    assert "does not match the staged text" in report.detail


LESSON_002_RULE = LESSON_001.replace("LL-001", "LL-002").replace("One", "Two").replace(
    "status: documented", "status: rule")
LEGACY_INDEX_RICH = (
    "# Lessons Learned Index\n\n**Last Updated:** 2024-01-01 (history)\n\n"
    "<!-- Previous: 2023-12-01 - older -->\n\n**Next available ID:** LL-003\n\n---\n\n"
    "## Master Table\n\n" + MASTER_HEADER + MASTER_SEP +
    "| LL-001 | Fixture Lesson One | process | medium | python | claude-code | PROC | fixture | documented |\n"
    "| LL-002 | Fixture Lesson Two | process | medium | python | claude-code | PROC | fixture | rule |\n"
    "\n---\n\n## Hand Notes\n\nA hand-written section.\n\n---\n\n"
    "## Rule Promotion Log\n\n| Date | Lesson ID | Artifact Created | File |\n"
    "|------|-----------|-----------------|------|\n| 2024-01-02 | LL-002 | a rule | [r](r.md) |\n\n---\n"
)
LEGACY_COMPANION = ("# Categorization\n\n**Last Updated:** 2024-01-01\n\n"
                    "## Cross-cutting observations\n\nA hand note.\n")


def _hash_tree(root: Path) -> dict:
    import hashlib
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


def _raise_in_build_ledger(monkeypatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError("ledger build crashed")
    monkeypatch.setattr(mig, "build_ledger", boom)


def _raise_in_companion_step(monkeypatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError("companion step crashed")
    monkeypatch.setattr(mig.gen, "_run_companion_cli", boom)


def _miss_in_verify(monkeypatch):
    monkeypatch.setattr(mig, "verify_written", lambda _plan: ["forced miss after every write landed"])


@pytest.mark.parametrize("inject", [_miss_in_verify, _raise_in_companion_step, _raise_in_build_ledger])
def test_write_failed_restores_the_whole_lessons_tree_byte_for_byte(tmp_path, monkeypatch, inject):
    cfg, lessons_dir = _project(tmp_path, LEGACY_INDEX_RICH)
    _write(lessons_dir / "Archive" / "LL-002-PROC-Two.md", LESSON_002_RULE)
    _write(lessons_dir / "00-Categorization-By-Domain.md", LEGACY_COMPANION)
    before = _hash_tree(lessons_dir)
    inject(monkeypatch)
    report = _migrate(cfg)
    assert report.state == "write_failed", report.detail
    assert _hash_tree(lessons_dir) == before
    backups = _pair(cfg) / "lessons"
    assert (backups / "00-Categorization-By-Domain.md").read_bytes() == LEGACY_COMPANION.encode("utf-8")


@pytest.mark.parametrize("fail", [False, True], ids=["migrated", "write_failed"])
def test_bootstrap_notes_seed_is_backed_up_replaced_and_restored_on_failure(tmp_path, monkeypatch, fail):
    cfg, lessons_dir = _project(tmp_path, LEGACY_INDEX_RICH)
    _write(lessons_dir / "Archive" / "LL-002-PROC-Two.md", LESSON_002_RULE)
    _write(lessons_dir / "00-Categorization-By-Domain.md", LEGACY_COMPANION)
    notes = lessons_dir / "00-Categorization-Notes-LessonsLearned.md"
    seed = lessons_bootstrap.NOTES_SEED_CONTENT.encode("utf-8")
    notes.write_bytes(seed)  # what the bootstrap writes on every upgrade before this step runs
    before = _hash_tree(lessons_dir)
    if fail:
        _miss_in_verify(monkeypatch)
    report = _migrate(cfg)
    assert report.state == ("write_failed" if fail else "migrated"), report.detail
    assert (_pair(cfg) / "lessons" / notes.name).read_bytes() == seed
    if fail:
        assert _hash_tree(lessons_dir) == before
    else:
        assert notes.read_bytes() == LEGACY_COMPANION.encode("utf-8")


def test_accepted_check_finding_reports_the_generator_clean(tmp_path):
    index = LEGACY_INDEX.replace("| fixture | documented |", "| fixture | applied |")
    cfg, _lessons_dir = _project(tmp_path, index)
    report = _migrate(cfg)
    assert report.state == "migrated", report.detail
    assert report.counts["generator_check_clean"] is True


def test_unexpected_exception_becomes_state_error(tmp_path, monkeypatch):
    cfg, _lessons_dir = _project(tmp_path)
    before = _snapshot(tmp_path)

    def boom(*args, **kwargs):
        raise RuntimeError("injected failure")
    monkeypatch.setattr(mig, "plan_migration", boom)
    report = _migrate(cfg)
    assert report.state == "error" and "injected failure" in report.detail
    assert _snapshot(tmp_path) == before


def test_routine_never_raises_even_on_a_wild_failure(tmp_path, monkeypatch):
    cfg, _lessons_dir = _project(tmp_path)

    def boom(*args, **kwargs):
        raise ValueError("anything")
    monkeypatch.setattr(sup, "classify_shape", boom)
    report = lm.migrate_lessons_if_legacy(cfg, "1.0", "1.1")  # must not raise
    assert report.state == "error" and "anything" in report.detail


# ---------------------------------------------------------------------------
# Disposition log, idempotence, banner
# ---------------------------------------------------------------------------


def test_one_disposition_row_per_written_file(tmp_path):
    cfg, _lessons_dir = _project(tmp_path)
    report = _migrate(cfg)
    assert report.state == "migrated"
    assert len(_disposition_rows(cfg)) == len(report.written) == len(set(report.written))


def test_second_call_after_migrated_is_generated_and_touches_nothing(tmp_path):
    cfg, _lessons_dir = _project(tmp_path)
    assert _migrate(cfg).state == "migrated"
    before = _snapshot(tmp_path)
    assert _migrate(cfg, ("1.1", "1.2")).state == "generated"
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize("state,headline", [
    ("migrated", "Lessons index migration:"),
    ("refused", "Lessons index migration: REFUSED"),
    ("unrecognized", "is not a hand-authored or generated index"),
    ("backup_failed", "Lessons index migration: BACKUP FAILED"),
    ("write_failed", "Lessons index migration: WRITE FAILED"),
    ("error", "Lessons index migration: ERROR"),
])
def test_banner_names_each_state(capsys, state, headline):
    report = lm.LessonsMigrationReport(
        state=state, index_path=Path("LessonsLearned") / "00-Index-LessonsLearned.md", detail="why",
        fix="do this\n" + lm.RERUN, counts={"shards": 1}, git_dirty=False)
    lm._emit_lessons_migration_banner(report)
    out = capsys.readouterr().out
    assert headline in out.splitlines()[0]
    if state == "refused":
        assert "  fix:    do this" in out and "then re-run /planwise upgrade" in out


def test_lessons_deferred_fix_names_no_flag(tmp_path):
    cfg, _lessons_dir = _project(tmp_path)
    report = lm.migrate_lessons_if_legacy(cfg, "1.0", "1.1", defer_legacy=True)
    assert report.state == "deferred", report.detail
    assert report.fix and "--" not in report.fix


@pytest.mark.parametrize("state", ["absent", "generated"])
def test_banner_is_silent_when_nothing_happened(capsys, state):
    lm._emit_lessons_migration_banner(lm.LessonsMigrationReport(state=state, index_path=None))
    assert capsys.readouterr().out == ""


def test_banner_never_raises_on_a_malformed_report(capsys):
    report = lm.LessonsMigrationReport(state="migrated", index_path=None, counts={})
    report.git_dirty = "not-a-bool"  # a malformed field the banner dict-lookup cannot key on
    lm._emit_lessons_migration_banner(report)  # must not raise
    assert "Lessons index migration:" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# DISPOSITIONS.md and the banner's backup count describe this run exactly
# ---------------------------------------------------------------------------

_ROW_RE = re.compile(r"^- \d{4}-\d{2}-\d{2} `([^`]+)` — ([^:]+): (.*)$")


def _disposition_rows(cfg) -> list:
    """(project-relative posix path, action, reason) per DISPOSITIONS.md row."""
    text = (_pair(cfg) / "DISPOSITIONS.md").read_text(encoding="utf-8")
    return [(Path(m.group(1)).as_posix(), m.group(2), m.group(3))
            for m in map(_ROW_RE.match, text.splitlines()) if m]


def _backup_files(cfg) -> set:
    root = _pair(cfg) / "lessons"
    return {p for p in root.rglob("*") if p.is_file()} if root.exists() else set()


def _banner_backups_line(report, capsys) -> str:
    lm._emit_lessons_migration_banner(report)
    return next(ln for ln in capsys.readouterr().out.splitlines() if ln.strip().startswith("backups:"))


def _banner_count(line: str) -> int:
    return int(re.search(r"\((\d+) file\(s\)", line).group(1))


def test_dispositions_cover_every_changed_path_and_the_banner_counts_this_runs_backups(tmp_path, capsys):
    cfg, lessons_dir = _project(tmp_path, LEGACY_INDEX_RICH)
    _write(lessons_dir / "Archive" / "LL-002-PROC-Two.md", LESSON_002_RULE)  # archived: the generator shards it
    _write(lessons_dir / "00-Categorization-By-Domain.md", LEGACY_COMPANION)
    before = _snapshot(lessons_dir)
    report = _migrate(cfg)
    assert report.state == "migrated", report.detail
    after = _snapshot(lessons_dir)

    def rel(key: str) -> str:
        return (lessons_dir / key).relative_to(cfg.project_root).as_posix()
    rows = _disposition_rows(cfg)
    logged = [path for path, _action, _reason in rows]
    assert len(logged) == len(set(logged))  # one row per file
    changed = {k for k in before.keys() | after.keys() if before.get(k) != after.get(k)}
    assert {rel(k) for k in changed} <= set(logged)
    by_rel = {rel(k): k for k in before.keys() | after.keys()}
    for path, action, _reason in rows:  # every action names what actually happened to the file
        key = by_rel[path]
        expected = ("lessons-created" if key not in before else "lessons-deleted" if key not in after
                    else "lessons-rewritten" if before[key] != after[key] else "lessons-unchanged")
        assert action == expected, (path, action)
    actions = {path: action for path, action, _reason in rows}
    assert actions[rel("00-Categorization-By-Domain.md")] == "lessons-rewritten"
    assert actions[rel("00-Categorization-Notes-LessonsLearned.md")] == "lessons-created"
    assert report.counts["shards"] >= 1
    shards = [k for k in after if k not in before and k.startswith("Archive/")]
    assert shards and all(actions[rel(k)] == "lessons-created" for k in shards)
    backed = _backup_files(cfg)
    backup_root = _pair(cfg) / "lessons"
    assert {rel(p.relative_to(backup_root).as_posix()) for p in backed} <= set(logged)
    assert _banner_count(_banner_backups_line(report, capsys)) == len(backed) == len(report.backed_up)


def test_banner_counts_only_this_runs_backups_and_labels_a_kept_one(tmp_path, capsys):
    cfg, lessons_dir = _project(tmp_path)
    kept = _pair(cfg) / "lessons" / "00-Index-LessonsLearned.md"
    _write(kept, LEGACY_INDEX)  # an earlier run in this version pair already made this pre-image
    report = _migrate(cfg)
    assert report.state == "migrated", report.detail
    made = _backup_files(cfg) - {kept}
    line = _banner_backups_line(report, capsys)
    assert _banner_count(line) == len(made) == len(report.backed_up)
    assert "1 kept from an earlier run" in line
    index_rel = (lessons_dir / "00-Index-LessonsLearned.md").relative_to(cfg.project_root).as_posix()
    reasons = {path: reason for path, _action, reason in _disposition_rows(cfg)}
    assert "kept, not overwritten" in reasons[index_rel]


# ---------------------------------------------------------------------------
# write_changelog_plan: a write failure that is not an OSError (here, text the
# UTF-8 encoder cannot write) still ends in write_failed with the tree
# restored, never a raised exception.
# ---------------------------------------------------------------------------


def test_a_non_oserror_write_failure_is_rolled_back_and_reported(tmp_path):
    lessons_dir = tmp_path / "LessonsLearned"
    lessons_dir.mkdir()
    existing = lessons_dir / "00-Changelog-LessonsLearned.md"
    existing.write_bytes(b"before\n")
    created = lessons_dir / "00-Changelog-LessonsLearned-Part-02.md"
    plan = {"outputs": [(created, "new part\n"), (existing, "a lone surrogate \ud800\n")], "remove": []}
    report = lm.LessonsMigrationReport(state="absent", index_path=None, backup_dir=tmp_path / "backups")
    rows = lm.write_changelog_plan(plan, lessons_dir, report, "re-run the command")
    assert rows is None
    assert report.state == "write_failed", report.detail
    assert existing.read_bytes() == b"before\n"
    assert not created.exists()
    assert sorted(p.name for p in lessons_dir.iterdir()) == [existing.name]  # no staged temp file left
