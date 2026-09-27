"""Wiring tests: does the retrofit actually run without a human step?

`test_backlog_migration.py` proves the migration routine itself is correct in
isolation (`migrate_backlog_if_legacy()` called directly). This file proves
the CALL SITES: `artifact_upgrade._run_upgrade()` reaches the routine on
BOTH of its exits (the already-up-to-date early return and the main upgrade
path), `init_project.main()` reaches it after the lessons bootstrap on a
fresh/legacy `init`, a refused migration surfaces as a loud SkippedArtifact
at init and never changes `--upgrade`'s exit code, and `--backlog-reconcile`
is validated and forwarded end to end.

Fixtures reuse `test_backlog_migration`'s project builder (a legacy backlog
under a real dev-tree plugin root) rather than reinventing one, per that
module's own docstring convention. Every InitConfig here points `plugin_root`
at the real dev tree: the installed cache carries neither the generator nor
the migrator, so a synthetic plugin root would fail before the wiring under
test ever ran.
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
from config_gen import InitConfig, read_plugin_version
from test_backlog_migration import AMBIG, AMBIG_BODY, TITLE
from test_backlog_migration import _project as _bm_project
from test_backlog_migration import legacy_index as _legacy_index_text

INIT_PROJECT = SCRIPTS / "init_project.py"
REAL_PLUGIN_ROOT = SCRIPTS.parent
TARGET_VERSION = read_plugin_version(REAL_PLUGIN_ROOT)  # measured live, never hardcoded


def _pin(cfg, pinned: str) -> None:
    """Prepend plugin_root/plugin_version to a fixture's config.yaml in place,
    so `_run_upgrade()`'s own pin-read and pin-commit logic has something to
    read — `test_backlog_migration._project()` writes a config with neither
    key, which is correct for driving `migrate_backlog_if_legacy()` directly
    but not for driving the full `_run_upgrade()` flow this file exercises."""
    config_path = cfg.project_root / "planwise" / "config.yaml"
    text = config_path.read_text(encoding="utf-8")
    posix_root = str(cfg.plugin_root).replace("\\", "/")
    config_path.write_text(
        f'plugin_root: "{posix_root}"\nplugin_version: "{pinned}"\n{text}',
        encoding="utf-8",
    )


def _legacy_project(tmp_path, pinned: str, **project_kwargs):
    """A legacy-backlog project, pinned at `pinned`, with an InitConfig whose
    plugin_version is the live one (so a caller passing pinned != TARGET_VERSION
    drives the main upgrade path, and pinned == TARGET_VERSION drives the
    already-up-to-date early return)."""
    cfg, backlog = _bm_project(tmp_path, **project_kwargs)
    _pin(cfg, pinned)
    cfg = InitConfig(
        project_name=cfg.project_name, project_root=cfg.project_root,
        plugin_root=cfg.plugin_root, plugin_version=TARGET_VERSION,
    )
    return cfg, backlog


def _read_config(cfg) -> dict:
    return yaml.safe_load((cfg.project_root / "planwise" / "config.yaml").read_text(encoding="utf-8")) or {}


# ---------------------------------------------------------------------------
# (a)-(c): artifact_upgrade._run_upgrade() reaches the routine on both exits.
# ---------------------------------------------------------------------------
def test_a_main_path_migrates_and_commits_the_pin(tmp_path, monkeypatch, capsys):
    cfg, _backlog = _legacy_project(tmp_path, pinned="1.0.5.1")
    monkeypatch.setattr(artifact_upgrade, "INSTALLED_RULES", [])

    exit_code = artifact_upgrade._run_upgrade(cfg)
    out = capsys.readouterr().out

    assert exit_code == 0
    assert "Backlog index migration:" in out
    assert "generator --check:      clean" in out
    assert _read_config(cfg)["plugin_version"] == TARGET_VERSION


def test_b_already_up_to_date_branch_still_migrates(tmp_path, monkeypatch, capsys):
    cfg, _backlog = _legacy_project(tmp_path, pinned=TARGET_VERSION)
    monkeypatch.setattr(artifact_upgrade, "INSTALLED_RULES", [])

    exit_code = artifact_upgrade._run_upgrade(cfg)
    out = capsys.readouterr().out

    assert exit_code == 0
    # The shared "Backlog index migration:" prefix alone does not distinguish
    # a migrated run from ERROR/REFUSED/WRITE FAILED/BACKUP FAILED, all of
    # which share it -- assert the migrated banner's own distinguishing line.
    assert "generator --check:      clean" in out
    assert out.rstrip().splitlines()[-1] == "Already up to date."
    # And the generated shape on disk: a second call on the same pair now
    # classifies the index as already-generated, never as legacy again.
    report = artifact_upgrade.migrate_backlog_if_legacy(cfg, TARGET_VERSION, TARGET_VERSION)
    assert report.state == "generated"


def test_c_refusal_never_changes_the_return_code_and_the_pin_still_commits(tmp_path, monkeypatch, capsys):
    # Reuse the ambiguous-unit fixture test_backlog_migration itself refuses on.
    cfg, _backlog = _legacy_project(
        tmp_path, pinned="1.0.5.1",
        index_text=_legacy_index_text(f"{TITLE}. {AMBIG}"), body1=AMBIG_BODY,
    )
    monkeypatch.setattr(artifact_upgrade, "INSTALLED_RULES", [])

    exit_code = artifact_upgrade._run_upgrade(cfg)
    out = capsys.readouterr().out

    assert exit_code == 0
    assert "REFUSED" in out
    assert _read_config(cfg)["plugin_version"] == TARGET_VERSION


# ---------------------------------------------------------------------------
# (d)-(e): init_project.main() reaches the routine after the lessons block.
# ---------------------------------------------------------------------------
def test_d_reinit_on_a_legacy_tree_migrates(tmp_path, monkeypatch, capsys):
    """A RE-init: this fixture's config.yaml already exists (via `_legacy_project`),
    so this is init running again on a project the user already set up, not a
    truly fresh one -- the fresh case is `test_d2` below."""
    # A plain `init` run (no --upgrade/--migrate/--doctor/...) falls off the
    # end of main() without calling sys.exit() — nothing to catch here.
    cfg, _backlog = _legacy_project(tmp_path, pinned=TARGET_VERSION)
    argv = ["init_project.py", "--name", cfg.project_name,
            "--project-root", str(cfg.project_root)]
    monkeypatch.setattr(sys, "argv", argv)

    ip.main()
    out = capsys.readouterr().out

    # The shared "Backlog index migration:" prefix alone does not distinguish
    # a migrated run from ERROR/REFUSED/WRITE FAILED/BACKUP FAILED.
    assert "generator --check:      clean" in out
    report = artifact_upgrade.migrate_backlog_if_legacy(cfg, TARGET_VERSION, TARGET_VERSION)
    assert report.state == "generated"


def test_d2_truly_fresh_init_with_no_config_yet_refuses_on_an_unmapped_abbrev(tmp_path, monkeypatch, capsys):
    """A truly fresh init: no config.yaml exists before this run, so init
    writes it fresh (in this same run, with no `abbreviations:` block). The
    legacy index's rows use abbrevs (SMP/INFRA) nothing in that fresh config
    supplies, so the migration correctly REFUSES rather than guessing --
    recognise-or-refuse, never best-effort. The refusal surfaces as a
    Skipped row naming the index, and never changes init's own exit code."""
    cfg, _backlog = _bm_project(tmp_path)
    (cfg.project_root / "planwise" / "config.yaml").unlink()
    argv = ["init_project.py", "--name", cfg.project_name,
            "--project-root", str(cfg.project_root)]
    monkeypatch.setattr(sys, "argv", argv)

    ip.main()  # falls off the end of main() -- no sys.exit() on a plain init
    out = capsys.readouterr().out

    assert "REFUSED" in out
    assert "Skipped (action required):" in out
    skipped_section = out.split("Skipped (action required):", 1)[1]
    assert "00-Index-Backlog.md" in skipped_section


def test_e_refused_init_names_the_index_under_skipped(tmp_path, monkeypatch, capsys):
    cfg, _backlog = _legacy_project(
        tmp_path, pinned=TARGET_VERSION,
        index_text=_legacy_index_text(f"{TITLE}. {AMBIG}"), body1=AMBIG_BODY,
    )
    argv = ["init_project.py", "--name", cfg.project_name,
            "--project-root", str(cfg.project_root)]
    monkeypatch.setattr(sys, "argv", argv)

    ip.main()
    out = capsys.readouterr().out

    assert "Skipped (action required):" in out
    skipped_section = out.split("Skipped (action required):", 1)[1]
    assert "00-Index-Backlog.md" in skipped_section
    assert "/planwise backlog" in skipped_section


# ---------------------------------------------------------------------------
# (f)-(g): --backlog-reconcile is argparse-guarded and forwarded as a kwarg.
# ---------------------------------------------------------------------------
def test_f_backlog_reconcile_without_upgrade_is_a_parser_error():
    result = subprocess.run(
        [sys.executable, str(INIT_PROJECT), "--name", "X",
         "--backlog-reconcile", "index-wins"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 2
    assert "--backlog-reconcile requires --upgrade" in result.stderr


def test_g_backlog_reconcile_with_upgrade_is_forwarded_as_a_kwarg(tmp_path, monkeypatch):
    calls = []
    real = artifact_upgrade.migrate_backlog_if_legacy

    def spy(cfg, from_version, to_version, *, reconcile=None):
        calls.append(reconcile)
        return real(cfg, from_version, to_version, reconcile=reconcile)

    monkeypatch.setattr(artifact_upgrade, "migrate_backlog_if_legacy", spy)
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
            "--upgrade", "--backlog-reconcile", "index-wins"]
    monkeypatch.setattr(sys, "argv", argv)

    with pytest.raises(SystemExit) as excinfo:
        ip.main()

    assert excinfo.value.code == 0
    assert calls == ["index-wins"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
