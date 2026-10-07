"""Wiring tests: does the plans retrofit actually run without a human step?

`test_plans_migration.py` proves the migration routine itself is correct in
isolation (`migrate_plans_if_legacy()` called directly). This file proves the
CALL SITES: `artifact_upgrade._run_upgrade()` reaches the routine on BOTH of its
exits (the already-up-to-date early return and the main upgrade path),
immediately after the lessons retrofit on each; `init_project.main()` reaches
it after the lessons retrofit on a fresh or legacy `init`; a refused,
unrecognized, backup-failed, write-failed or errored migration surfaces as a
loud SkippedArtifact at init and never changes `--upgrade`'s exit code; a
routine that raises is caught on both exits; and a plans index that init seeds
itself is rendered through the generator, so its Status Legend follows the
config's `plan_statuses:`.

Fixtures reuse `test_lessons_migration`'s project builder (a real project under
a real dev-tree plugin root) rather than reinventing one. Every InitConfig here
points `plugin_root` at the real dev tree: the installed cache carries neither
the generator nor the migrators, so a synthetic plugin root would fail before
the wiring under test ever ran.
"""
import os
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
import plans_migration as pm
from config_gen import InitConfig, read_plugin_version
from test_lessons_migration import _project as _lm_project

REAL_PLUGIN_ROOT = SCRIPTS.parent
TARGET_VERSION = read_plugin_version(REAL_PLUGIN_ROOT)  # measured live, never hardcoded
SEED = REAL_PLUGIN_ROOT / "seed" / "00-Index-Plans.md"


def _pin(cfg, pinned: str) -> None:
    """Prepend plugin_root/plugin_version to a fixture's config.yaml in place,
    so `_run_upgrade()`'s own pin-read and pin-commit logic has something to read."""
    config_path = cfg.project_root / "planwise" / "config.yaml"
    text = config_path.read_text(encoding="utf-8")
    posix_root = str(cfg.plugin_root).replace("\\", "/")
    config_path.write_text(
        f'plugin_root: "{posix_root}"\nplugin_version: "{pinned}"\n{text}',
        encoding="utf-8",
    )


def _project(tmp_path, pinned: str):
    """A pinned project whose InitConfig carries the live plugin version, so a
    caller passing pinned != TARGET_VERSION drives the main upgrade path and
    pinned == TARGET_VERSION drives the already-up-to-date early return. No
    plans index is seeded, so the real plans routine stays `absent` wherever a
    test does not patch it."""
    cfg, _lessons_dir = _lm_project(tmp_path)
    _pin(cfg, pinned)
    return InitConfig(
        project_name=cfg.project_name, project_root=cfg.project_root,
        plugin_root=cfg.plugin_root, plugin_version=TARGET_VERSION,
    )


def _read_config(cfg) -> dict:
    return yaml.safe_load((cfg.project_root / "planwise" / "config.yaml").read_text(encoding="utf-8")) or {}


def _canned(state: str, index_path=None, **fields) -> pm.PlansMigrationReport:
    return pm.PlansMigrationReport(state=state, index_path=index_path, **fields)


def _init_argv(monkeypatch, cfg) -> None:
    monkeypatch.setattr(sys, "argv", ["init_project.py", "--name", cfg.project_name,
                                      "--project-root", str(cfg.project_root)])


# ---------------------------------------------------------------------------
# (a)-(b): artifact_upgrade._run_upgrade() reaches the routine on both exits,
# once, with the version pair and AFTER the lessons routine.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("branch", ["main", "already-up-to-date"])
def test_a_run_upgrade_calls_the_plans_routine_once_with_the_pair_after_lessons(tmp_path, monkeypatch, capsys, branch):
    """Proves the caller: both exits of _run_upgrade()."""
    pinned = "1.0.5.1" if branch == "main" else TARGET_VERSION
    cfg = _project(tmp_path, pinned)
    monkeypatch.setattr(artifact_upgrade, "INSTALLED_RULES", [])
    order = []

    def lessons_spy(cfg_, from_version, to_version, *, reconcile=None, defer_legacy=False):
        order.append("lessons")
        return pm.PlansMigrationReport(state="absent", index_path=None)

    def plans_spy(cfg_, from_version, to_version, **kwargs):
        order.append(("plans", from_version, to_version, kwargs))
        return _canned("refused", Path("x"), detail="a reason", fix="a fix")

    monkeypatch.setattr(artifact_upgrade, "migrate_lessons_if_legacy", lessons_spy)
    monkeypatch.setattr(artifact_upgrade, "migrate_plans_if_legacy", plans_spy)

    exit_code = artifact_upgrade._run_upgrade(cfg)
    out = capsys.readouterr().out

    assert exit_code == 0
    assert order == ["lessons", ("plans", pinned, TARGET_VERSION, {})]
    assert "Plans index migration: REFUSED" in out


# ---------------------------------------------------------------------------
# (c): a refusal never changes the exit code or blocks the pin commit.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("branch", ["main", "already-up-to-date"])
def test_b_a_refused_report_leaves_the_exit_code_and_the_pin_alone(tmp_path, monkeypatch, capsys, branch):
    """Proves the caller: both exits of _run_upgrade() ignore a refusal."""
    pinned = "1.0.5.1" if branch == "main" else TARGET_VERSION
    cfg = _project(tmp_path, pinned)
    monkeypatch.setattr(artifact_upgrade, "INSTALLED_RULES", [])
    refused = _canned("refused", Path("x"), detail="a reason", fix="a fix")
    monkeypatch.setattr(artifact_upgrade, "migrate_plans_if_legacy", lambda *a, **k: refused)

    exit_code = artifact_upgrade._run_upgrade(cfg)
    out = capsys.readouterr().out

    assert exit_code == 0
    assert "REFUSED" in out
    assert _read_config(cfg)["plugin_version"] == TARGET_VERSION


# ---------------------------------------------------------------------------
# (d): a routine that raises is caught: warning on stderr, exit code unchanged.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("branch", ["main", "already-up-to-date"])
def test_c_a_raising_routine_is_caught_with_a_warning_and_the_exit_code_unchanged(
    tmp_path, monkeypatch, capsys, branch,
):
    """Proves the caller: the try/except around step 2f on both exits."""
    pinned = "1.0.5.1" if branch == "main" else TARGET_VERSION
    cfg = _project(tmp_path, pinned)
    monkeypatch.setattr(artifact_upgrade, "INSTALLED_RULES", [])

    def boom(*args, **kwargs):
        raise RuntimeError("plans routine exploded")
    monkeypatch.setattr(artifact_upgrade, "migrate_plans_if_legacy", boom)

    exit_code = artifact_upgrade._run_upgrade(cfg)
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "plans index migration step raised unexpectedly: plans routine exploded" in captured.err
    assert _read_config(cfg)["plugin_version"] == TARGET_VERSION


# ---------------------------------------------------------------------------
# (e): init_project.main() reaches the routine after the lessons routine,
# with the ("init", version) pair.
# ---------------------------------------------------------------------------
def test_d_init_calls_the_plans_routine_with_init_and_the_live_version_after_lessons(tmp_path, monkeypatch, capsys):
    """Proves the caller: init_project.main()."""
    cfg = _project(tmp_path, TARGET_VERSION)
    order = []

    def lessons_spy(cfg_, from_version, to_version, *, reconcile=None, defer_legacy=False):
        order.append("lessons")
        return pm.PlansMigrationReport(state="absent", index_path=None)

    def plans_spy(cfg_, from_version, to_version, **kwargs):
        order.append(("plans", from_version, to_version, kwargs))
        return _canned("refused", Path("x"), detail="a reason", fix="a fix")

    monkeypatch.setattr(ip, "migrate_lessons_if_legacy", lessons_spy)
    monkeypatch.setattr(ip, "migrate_plans_if_legacy", plans_spy)
    _init_argv(monkeypatch, cfg)

    ip.main()
    out = capsys.readouterr().out

    # Plain init is detect-only: it passes defer_legacy=True and chooses no reconcile mode.
    assert order == ["lessons", ("plans", "init", TARGET_VERSION, {"defer_legacy": True})]
    assert "Plans index migration: REFUSED" in out


# ---------------------------------------------------------------------------
# (f): the deferred state and the five refusal states append one SkippedArtifact
# carrying the report's own fix; the three non-failure states append none.
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
def test_e_skipped_artifact_is_appended_for_the_deferred_and_refusal_states_only(
    tmp_path, monkeypatch, capsys, state, should_skip,
):
    """Proves the caller: init_project.main()'s SkippedArtifact mapping."""
    cfg = _project(tmp_path, TARGET_VERSION)
    plans_index = cfg.project_root / "planwise" / "Plans" / "00-Index-Plans.md"
    index_path = None if state == "absent" else plans_index
    canned = _canned(state, index_path, detail="the reason", fix="the fix")
    monkeypatch.setattr(ip, "migrate_plans_if_legacy", lambda *a, **k: canned)
    _init_argv(monkeypatch, cfg)

    ip.main()
    out = capsys.readouterr().out
    skipped = out.split("Skipped (action required):", 1)[1] if "Skipped (action required):" in out else ""

    if should_skip:
        assert str(plans_index) in skipped
        assert "the fix" in skipped
        assert "the reason" in skipped
        assert "/planwise list, /planwise doctor Stage 11" in skipped
    else:
        assert str(plans_index) not in skipped
        assert "the fix" not in skipped


def test_f_an_error_with_no_index_path_is_left_to_the_config_row(tmp_path, monkeypatch, capsys):
    """Proves the caller: the `error` and `index_path is None` pass-through."""
    cfg = _project(tmp_path, TARGET_VERSION)
    canned = _canned("error", None, detail="the reason", fix="the fix")
    monkeypatch.setattr(ip, "migrate_plans_if_legacy", lambda *a, **k: canned)
    _init_argv(monkeypatch, cfg)

    ip.main()
    out = capsys.readouterr().out

    assert "the fix" not in (out.split("Skipped (action required):", 1)[1] if "Skipped (action required):" in out else "")


def test_g_the_fallback_index_path_follows_the_configured_index_name(tmp_path, monkeypatch, capsys):
    """Proves the caller: no literal index filename in the SkippedArtifact fallback."""
    cfg = _project(tmp_path, TARGET_VERSION)
    config_path = cfg.project_root / "planwise" / "config.yaml"
    config_path.write_text(config_path.read_text(encoding="utf-8")
                           + "\nproject:\n  index_files:\n    plans: 00-Plans-Custom.md\n", encoding="utf-8")
    canned = _canned("refused", None, detail="the reason", fix="the fix")
    monkeypatch.setattr(ip, "migrate_plans_if_legacy", lambda *a, **k: canned)
    _init_argv(monkeypatch, cfg)

    ip.main()
    out = capsys.readouterr().out

    assert "00-Plans-Custom.md" in out.split("Skipped (action required):", 1)[1]


# ---------------------------------------------------------------------------
# (g): the banner's own first line, quoted from the shipped code, prints at
# every wired call site on a non-silent state. Patches nothing inside the banner.
# ---------------------------------------------------------------------------
def test_h_the_banners_own_first_line_prints_at_every_wired_call_site(tmp_path, monkeypatch, capsys):
    """Proves the caller: the two _run_upgrade() exits and init_project.main()
    all reach the REAL `_emit_plans_migration_banner`. The expected line comes
    from `plans_migration._banner_lines` itself, never from this file's prose."""
    report = _canned("refused", Path("x"), detail="a reason", fix="a fix")
    expected_first_line = pm._banner_lines(report)[0]
    assert expected_first_line.startswith("Plans index migration:")

    cfg_a = _project(tmp_path / "a", "1.0.5.1")
    monkeypatch.setattr(artifact_upgrade, "INSTALLED_RULES", [])
    monkeypatch.setattr(artifact_upgrade, "migrate_plans_if_legacy", lambda *a, **k: report)
    artifact_upgrade._run_upgrade(cfg_a)
    assert expected_first_line in capsys.readouterr().out.splitlines()

    cfg_b = _project(tmp_path / "b", TARGET_VERSION)
    artifact_upgrade._run_upgrade(cfg_b)
    assert expected_first_line in capsys.readouterr().out.splitlines()

    cfg_c = _project(tmp_path / "c", TARGET_VERSION)
    monkeypatch.setattr(ip, "migrate_plans_if_legacy", lambda *a, **k: report)
    _init_argv(monkeypatch, cfg_c)
    ip.main()
    assert expected_first_line in capsys.readouterr().out.splitlines()


# ---------------------------------------------------------------------------
# (h): a plans index init seeds itself is rendered through the generator, so its
# Status Legend follows `plan_statuses:`; an existing index is never overwritten.
# ---------------------------------------------------------------------------
def _fresh_project(tmp_path, statuses=None):
    root = tmp_path / "proj"
    (root / "planwise").mkdir(parents=True)
    text = 'project:\n  name: "Fresh"\n  planwise_root: "planwise"\n  plans_dir: "Plans"\n'
    if statuses:
        text += "plan_statuses:\n" + "".join(f"  - {s}\n" for s in statuses)
    (root / "planwise" / "config.yaml").write_text(text, encoding="utf-8")
    return InitConfig(project_name="Fresh", project_root=root, plugin_root=REAL_PLUGIN_ROOT,
                      plugin_version=TARGET_VERSION)


def _check_exit(cfg) -> int:
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "generate_plans_index.py"),
         "--config", str(cfg.project_root / "planwise" / "config.yaml"), "--check"],
        capture_output=True, text=True, check=False, env=env,
    ).returncode


def test_i_a_fresh_init_with_custom_plan_statuses_passes_the_generator_check(tmp_path, monkeypatch, capsys):
    cfg = _fresh_project(tmp_path, statuses=["DRAFT", "SHIPPED"])
    index = cfg.project_root / "planwise" / "Plans" / "00-Index-Plans.md"
    _init_argv(monkeypatch, cfg)

    ip.main()
    out = capsys.readouterr().out

    legend = index.read_text(encoding="utf-8").split("## Status Legend", 1)[1]
    assert "| DRAFT |" in legend and "| SHIPPED |" in legend and "NOT_STARTED" not in legend
    assert _check_exit(cfg) == 0
    assert "rendered with the configured plan_statuses" in out


def test_j_a_fresh_init_with_the_default_statuses_keeps_the_seed_bytes(tmp_path, monkeypatch, capsys):
    cfg = _fresh_project(tmp_path)
    index = cfg.project_root / "planwise" / "Plans" / "00-Index-Plans.md"
    _init_argv(monkeypatch, cfg)

    ip.main()
    out = capsys.readouterr().out

    assert index.read_bytes() == SEED.read_bytes()
    assert _check_exit(cfg) == 0
    assert "rendered with the configured plan_statuses" not in out


@pytest.mark.parametrize("body", [
    b"# Our plans\r\n\r\nWe track plans in a spreadsheet now.\r\n",
    (b"# Plans Index\n\n| Abbrev | Name | Status | Created | Last Updated | Path |\n"
     b"|--------|------|--------|---------|--------------|------|\n"
     b"| ALP | Alpha | COMPLETE | 2026-01-10 | 2026-01-20 | Alpha/ |\n"),
], ids=["unrecognized", "hand-authored"])
def test_k_an_existing_index_of_any_shape_is_never_overwritten_by_init(tmp_path, monkeypatch, capsys, body):
    cfg = _fresh_project(tmp_path, statuses=["DRAFT", "SHIPPED"])
    index = cfg.project_root / "planwise" / "Plans" / "00-Index-Plans.md"
    index.parent.mkdir(parents=True)
    index.write_bytes(body)
    monkeypatch.setattr(ip, "migrate_plans_if_legacy", lambda *a, **k: _canned("absent"))  # isolate the seed render
    _init_argv(monkeypatch, cfg)

    ip.main()
    capsys.readouterr()

    assert index.read_bytes() == body


def test_l_the_render_helper_is_a_no_op_for_an_index_init_did_not_seed(tmp_path):
    cfg = _fresh_project(tmp_path, statuses=["DRAFT", "SHIPPED"])
    index = cfg.project_root / "planwise" / "Plans" / "00-Index-Plans.md"
    index.parent.mkdir(parents=True)
    index.write_bytes(SEED.read_bytes())

    assert ip.render_new_plans_index(cfg, seeds=[]) is None
    assert index.read_bytes() == SEED.read_bytes()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
