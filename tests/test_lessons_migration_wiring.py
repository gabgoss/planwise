"""Wiring tests: does the lessons retrofit actually run without a human step?

`test_lessons_migration.py` proves the migration routine itself is correct in
isolation (`migrate_lessons_if_legacy()` called directly). This file proves
the CALL SITES: `artifact_upgrade._run_upgrade()` reaches the routine on
BOTH of its exits (the already-up-to-date early return and the main upgrade
path), immediately after the backlog retrofit on each; `init_project.main()`
reaches it after the lessons bootstrap AND the backlog retrofit on a
fresh/legacy `init`; a refused/unrecognized/backup-failed migration surfaces
as a loud SkippedArtifact at init and never changes `--upgrade`'s exit code;
`--lessons-reconcile` is validated and forwarded end to end; and the lessons
bootstrap runs before the lessons migration at both entry points.

Fixtures reuse `test_lessons_migration`'s project builder (a legacy lessons
index under a real dev-tree plugin root) rather than reinventing one, per
that module's own docstring convention. Every InitConfig here points
`plugin_root` at the real dev tree: the installed cache carries neither the
generator nor the migrator, so a synthetic plugin root would fail before the
wiring under test ever ran.
"""
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

SCRIPTS = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ itself, for the sibling import below

import artifact_upgrade
import init_project as ip
import lessons_migration as lm
from config_gen import InitConfig, read_plugin_version
from test_lessons_migration import _project as _lm_project

INIT_PROJECT = SCRIPTS / "init_project.py"
REAL_PLUGIN_ROOT = SCRIPTS.parent
TARGET_VERSION = read_plugin_version(REAL_PLUGIN_ROOT)  # measured live, never hardcoded


def _pin(cfg, pinned: str) -> None:
    """Prepend plugin_root/plugin_version to a fixture's config.yaml in place,
    so `_run_upgrade()`'s own pin-read and pin-commit logic has something to
    read -- `test_lessons_migration._project()` writes a config with neither
    key, which is correct for driving `migrate_lessons_if_legacy()` directly
    but not for driving the full `_run_upgrade()` flow this file exercises."""
    config_path = cfg.project_root / "planwise" / "config.yaml"
    text = config_path.read_text(encoding="utf-8")
    posix_root = str(cfg.plugin_root).replace("\\", "/")
    config_path.write_text(
        f'plugin_root: "{posix_root}"\nplugin_version: "{pinned}"\n{text}',
        encoding="utf-8",
    )


def _legacy_project(tmp_path, pinned: str, **project_kwargs):
    """A legacy-lessons project, pinned at `pinned`, with an InitConfig whose
    plugin_version is the live one (so a caller passing pinned != TARGET_VERSION
    drives the main upgrade path, and pinned == TARGET_VERSION drives the
    already-up-to-date early return). No backlog index is seeded, so the
    backlog retrofit this wiring also calls stays state `absent` throughout
    -- it never interferes with the lessons assertions below."""
    cfg, lessons_dir = _lm_project(tmp_path, **project_kwargs)
    _pin(cfg, pinned)
    cfg = InitConfig(
        project_name=cfg.project_name, project_root=cfg.project_root,
        plugin_root=cfg.plugin_root, plugin_version=TARGET_VERSION,
    )
    return cfg, lessons_dir


def _read_config(cfg) -> dict:
    return yaml.safe_load((cfg.project_root / "planwise" / "config.yaml").read_text(encoding="utf-8")) or {}


def _canned(state: str, index_path=None, **fields) -> lm.LessonsMigrationReport:
    return lm.LessonsMigrationReport(state=state, index_path=index_path, **fields)


# ---------------------------------------------------------------------------
# (a)-(c): artifact_upgrade._run_upgrade() reaches the routine on both exits,
# immediately after the backlog retrofit, with the version pair.
# ---------------------------------------------------------------------------
def test_a_main_path_calls_lessons_routine_once_with_the_pair_and_emits_banner(tmp_path, monkeypatch, capsys):
    """Proves the caller: _run_upgrade()'s main upgrade path."""
    cfg, lessons_dir = _legacy_project(tmp_path, pinned="1.0.5.1")
    monkeypatch.setattr(artifact_upgrade, "INSTALLED_RULES", [])
    calls = []
    canned = _canned("migrated", lessons_dir / "00-Index-LessonsLearned.md", counts={"shards": 1}, git_dirty=False)

    def spy(cfg_, from_version, to_version, *, reconcile=None):
        calls.append((from_version, to_version, reconcile))
        return canned
    monkeypatch.setattr(artifact_upgrade, "migrate_lessons_if_legacy", spy)

    exit_code = artifact_upgrade._run_upgrade(cfg)
    out = capsys.readouterr().out

    assert exit_code == 0
    assert calls == [("1.0.5.1", TARGET_VERSION, None)]
    assert "Lessons index migration:" in out


def test_b_already_up_to_date_branch_calls_lessons_routine_once_with_the_pair(tmp_path, monkeypatch, capsys):
    """Proves the caller: _run_upgrade()'s already-up-to-date early return."""
    cfg, lessons_dir = _legacy_project(tmp_path, pinned=TARGET_VERSION)
    monkeypatch.setattr(artifact_upgrade, "INSTALLED_RULES", [])
    calls = []
    canned = _canned("migrated", lessons_dir / "00-Index-LessonsLearned.md", counts={"shards": 1}, git_dirty=False)

    def spy(cfg_, from_version, to_version, *, reconcile=None):
        calls.append((from_version, to_version, reconcile))
        return canned
    monkeypatch.setattr(artifact_upgrade, "migrate_lessons_if_legacy", spy)

    exit_code = artifact_upgrade._run_upgrade(cfg)
    out = capsys.readouterr().out

    assert exit_code == 0
    assert calls == [(TARGET_VERSION, TARGET_VERSION, None)]
    assert "Lessons index migration:" in out
    assert out.rstrip().splitlines()[-1] == "Already up to date."


def test_c_refused_report_never_changes_the_exit_code_and_the_pin_still_commits(tmp_path, monkeypatch, capsys):
    """Proves the caller: _run_upgrade()'s main path never lets a refusal
    from the lessons routine change the exit code or block the version-pin
    commit -- mirrors the backlog's own refusal-isolation guarantee."""
    cfg, _lessons_dir = _legacy_project(tmp_path, pinned="1.0.5.1")
    monkeypatch.setattr(artifact_upgrade, "INSTALLED_RULES", [])
    refused = _canned("refused", Path("x"), detail="a reason", fix="a fix")
    monkeypatch.setattr(artifact_upgrade, "migrate_lessons_if_legacy", lambda *a, **k: refused)

    exit_code = artifact_upgrade._run_upgrade(cfg)
    out = capsys.readouterr().out

    assert exit_code == 0
    assert "REFUSED" in out
    assert _read_config(cfg)["plugin_version"] == TARGET_VERSION


# ---------------------------------------------------------------------------
# (d): init_project.main() reaches the routine after the bootstrap AND the
# backlog retrofit, with the ("init", version) pair.
# ---------------------------------------------------------------------------
def test_d_init_calls_lessons_routine_with_init_and_the_live_version(tmp_path, monkeypatch, capsys):
    """Proves the caller: init_project.main()."""
    cfg, _lessons_dir = _legacy_project(tmp_path, pinned=TARGET_VERSION)
    calls = []
    canned = _canned("migrated", None, counts={"shards": 1}, git_dirty=False)

    def spy(cfg_, from_version, to_version, *, reconcile=None, defer_legacy=False):
        calls.append((from_version, to_version, reconcile, defer_legacy))
        return canned
    monkeypatch.setattr(ip, "migrate_lessons_if_legacy", spy)
    argv = ["init_project.py", "--name", cfg.project_name,
            "--project-root", str(cfg.project_root)]
    monkeypatch.setattr(sys, "argv", argv)

    ip.main()
    out = capsys.readouterr().out

    # Plain init is detect-only: defer_legacy=True, and no reconcile mode is chosen.
    assert calls == [("init", TARGET_VERSION, None, True)]
    assert "Lessons index migration:" in out


# ---------------------------------------------------------------------------
# (e): the six states init_project.py's backlog block uses --
# `{"deferred", "refused", "unrecognized", "backup_failed", "write_failed", "error"}`
# (init_project.py's backlog block, quoted verbatim) -- each append exactly
# one SkippedArtifact carrying the routine's own fix; the non-failure states
# append none.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("state,should_skip", [
    ("deferred", True),
    ("refused", True),
    ("unrecognized", True),
    ("backup_failed", True),
    ("write_failed", True),
    ("error", True),
    ("migrated", False),
    ("generated", False),
    ("absent", False),
])
def test_e_skipped_artifact_appended_for_the_same_six_states_the_backlog_block_uses(
    tmp_path, monkeypatch, capsys, state, should_skip,
):
    """Proves the caller: init_project.main()'s SkippedArtifact mapping,
    mirrored onto BCR's own backlog-block state set for sibling parity."""
    cfg, lessons_dir = _legacy_project(tmp_path, pinned=TARGET_VERSION)
    index_path = None if state == "absent" else lessons_dir / "00-Index-LessonsLearned.md"
    canned = _canned(state, index_path, detail="the reason", fix="the fix")
    monkeypatch.setattr(ip, "migrate_lessons_if_legacy", lambda *a, **k: canned)
    argv = ["init_project.py", "--name", cfg.project_name,
            "--project-root", str(cfg.project_root)]
    monkeypatch.setattr(sys, "argv", argv)

    ip.main()
    out = capsys.readouterr().out

    if should_skip:
        assert "Skipped (action required):" in out
        skipped_section = out.split("Skipped (action required):", 1)[1]
        assert str(index_path) in skipped_section
        assert "the fix" in skipped_section
        assert "/planwise lessons" in skipped_section
    else:
        skipped_section = out.split("Skipped (action required):", 1)[1] if "Skipped (action required):" in out else ""
        assert str(index_path) not in skipped_section if index_path else "the fix" not in skipped_section


# ---------------------------------------------------------------------------
# (f)-(g): --lessons-reconcile is argparse-guarded and forwarded as a kwarg.
# ---------------------------------------------------------------------------
def test_f_lessons_reconcile_without_upgrade_is_a_parser_error():
    """Proves the caller: init_project.py's argparse block."""
    result = subprocess.run(
        [sys.executable, str(INIT_PROJECT), "--name", "X",
         "--lessons-reconcile", "index-wins"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 2
    assert "--lessons-reconcile requires --upgrade" in result.stderr


def test_g_lessons_reconcile_with_upgrade_is_forwarded_to_run_upgrade(tmp_path, monkeypatch):
    """Proves the caller: init_project.main() -> _run_upgrade()'s own
    `lessons_reconcile` kwarg, end to end through argparse."""
    calls = []
    real = artifact_upgrade.migrate_lessons_if_legacy

    def spy(cfg, from_version, to_version, *, reconcile=None):
        calls.append(reconcile)
        return real(cfg, from_version, to_version, reconcile=reconcile)

    monkeypatch.setattr(artifact_upgrade, "migrate_lessons_if_legacy", spy)
    monkeypatch.setattr(artifact_upgrade, "INSTALLED_RULES", [])

    project_root = tmp_path / "proj"
    planwise_dir = project_root / "planwise"
    planwise_dir.mkdir(parents=True)
    posix_root = str(REAL_PLUGIN_ROOT).replace("\\", "/")
    (planwise_dir / "config.yaml").write_text(
        f'plugin_root: "{posix_root}"\nplugin_version: "0.0.0"\n'
        'project:\n  name: "spy-project"\n',
        encoding="utf-8",
    )
    argv = ["init_project.py", "--name", "spy-project",
            "--project-root", str(project_root),
            "--upgrade", "--lessons-reconcile", "index-wins"]
    monkeypatch.setattr(sys, "argv", argv)

    with pytest.raises(SystemExit) as excinfo:
        ip.main()

    assert excinfo.value.code == 0
    assert calls == ["index-wins"]


# ---------------------------------------------------------------------------
# (h)-(i): the lessons bootstrap runs before the lessons migration, at both
# entry points.
# ---------------------------------------------------------------------------
def test_h_bootstrap_runs_before_the_lessons_migration_in_run_upgrade(tmp_path, monkeypatch):
    """Proves the caller: _run_upgrade()'s main path order (bootstrap, then
    the backlog retrofit, then the lessons retrofit -- Session 04 flag 3's
    ordering, asserted here with a shared call-order list)."""
    cfg, _lessons_dir = _legacy_project(tmp_path, pinned="1.0.5.1")
    monkeypatch.setattr(artifact_upgrade, "INSTALLED_RULES", [])
    order = []
    real_bootstrap = artifact_upgrade.bootstrap_lessons_artifacts

    def bootstrap_spy(cfg_):
        order.append("bootstrap")
        return real_bootstrap(cfg_)

    def migrate_spy(cfg_, from_version, to_version, *, reconcile=None):
        order.append("lessons_migrate")
        return _canned("absent", None)
    monkeypatch.setattr(artifact_upgrade, "bootstrap_lessons_artifacts", bootstrap_spy)
    monkeypatch.setattr(artifact_upgrade, "migrate_lessons_if_legacy", migrate_spy)

    artifact_upgrade._run_upgrade(cfg)

    assert order == ["bootstrap", "lessons_migrate"]


def test_i_bootstrap_runs_before_the_lessons_migration_in_init_main(tmp_path, monkeypatch):
    """Proves the caller: init_project.main()'s order (bootstrap, then the
    backlog retrofit, then the lessons retrofit), asserted with a shared
    call-order list -- the bootstrap must have seeded the openers first."""
    cfg, _lessons_dir = _legacy_project(tmp_path, pinned=TARGET_VERSION)
    order = []
    real_bootstrap = ip.bootstrap_lessons_artifacts

    def bootstrap_spy(cfg_):
        order.append("bootstrap")
        return real_bootstrap(cfg_)

    def migrate_spy(cfg_, from_version, to_version, *, reconcile=None, defer_legacy=False):
        order.append("lessons_migrate")
        return _canned("absent", None)
    monkeypatch.setattr(ip, "bootstrap_lessons_artifacts", bootstrap_spy)
    monkeypatch.setattr(ip, "migrate_lessons_if_legacy", migrate_spy)
    argv = ["init_project.py", "--name", cfg.project_name,
            "--project-root", str(cfg.project_root)]
    monkeypatch.setattr(sys, "argv", argv)

    ip.main()

    assert order == ["bootstrap", "lessons_migrate"]


# ---------------------------------------------------------------------------
# (j): the banner's own first line -- never plan prose -- prints at every
# wired call site on a non-silent state. Patches nothing inside the banner.
# ---------------------------------------------------------------------------
def test_j_the_banners_own_first_line_prints_at_every_wired_call_site(tmp_path, monkeypatch, capsys):
    """Proves the caller: all three wired call sites (the two _run_upgrade()
    exits and init_project.main()) actually invoke the REAL, unpatched
    `_emit_lessons_migration_banner` / `_banner_lines` -- the first line
    quoted below comes from `lessons_migration._banner_lines` itself, never
    from this task's own prose."""
    report = lm.LessonsMigrationReport(
        state="refused", index_path=Path("x"), detail="a reason", fix="a fix")
    expected_first_line = lm._banner_lines(report)[0]
    assert expected_first_line == "Lessons index migration: REFUSED (index and lesson files left untouched)"

    # (1) _run_upgrade() main path
    cfg_a, _ld_a = _legacy_project(tmp_path / "a", pinned="1.0.5.1")
    monkeypatch.setattr(artifact_upgrade, "INSTALLED_RULES", [])
    monkeypatch.setattr(artifact_upgrade, "migrate_lessons_if_legacy", lambda *a, **k: report)
    artifact_upgrade._run_upgrade(cfg_a)
    assert expected_first_line in capsys.readouterr().out.splitlines()

    # (2) _run_upgrade() already-up-to-date early return
    cfg_b, _ld_b = _legacy_project(tmp_path / "b", pinned=TARGET_VERSION)
    monkeypatch.setattr(artifact_upgrade, "migrate_lessons_if_legacy", lambda *a, **k: report)
    artifact_upgrade._run_upgrade(cfg_b)
    assert expected_first_line in capsys.readouterr().out.splitlines()

    # (3) init_project.main()
    cfg_c, _ld_c = _legacy_project(tmp_path / "c", pinned=TARGET_VERSION)
    monkeypatch.setattr(ip, "migrate_lessons_if_legacy", lambda *a, **k: report)
    argv = ["init_project.py", "--name", cfg_c.project_name,
            "--project-root", str(cfg_c.project_root)]
    monkeypatch.setattr(sys, "argv", argv)
    ip.main()
    assert expected_first_line in capsys.readouterr().out.splitlines()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
