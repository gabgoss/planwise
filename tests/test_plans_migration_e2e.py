"""End-to-end tests for the plans-index retrofit: a legacy 1.0.5.1 plans index
reaches the generated shape with zero human steps, through both
`artifact_upgrade._run_upgrade` and a fresh `init_project.main()`. Mirrors
`test_lessons_migration_e2e.py`'s mechanics (byte-built fixture, git init and
commit, capture, tree snapshot) on the plans retrofit's own contract
(`plans_migration.py`, `migrate_plans_index.py`).

The fixture is Fixture B, built from the byte constants `test_migrate_plans_index`
carries: a hand-authored index whose Paths all carry the `Plans/` prefix, whose
Alpha row has a two-plan family (a Meta plan and an Exec plan), whose Beta row
has only a Meta plan, and whose Gamma row has an emoji status cell. Every
write is byte-built (`bytes`), never `write_text`, so a CRLF source keeps its
line endings.

Cost guard (`.claude/rules/guard-at-the-cost-layer.md`): the git init and
commit live inside the `_project` fixture-building function itself, so a
deselected run of this module builds nothing.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ itself, for the sibling import below

# `init_project` (the composition root) is imported first by convention,
# mirroring the lessons e2e module, so the import-order trap never fires.
import init_project as ip  # noqa: I001 -- composition root first, see comment above
import artifact_upgrade
import config_loader
import generate_plans_index as gen
import migrate_plans_index as mig
from config_gen import InitConfig, read_plugin_version
from test_migrate_plans_index import B_LINES, B_PLANS, build, legacy_index

REAL_PLUGIN_ROOT = SCRIPTS.parent
FROM = "1.0.5.1"
TO = read_plugin_version(REAL_PLUGIN_ROOT)  # measured live, never hardcoded
INDEX = "00-Index-Plans.md"
ALPHA_EXEC = "Alpha/Exec-ALP/ALP-Master-Plan.md"
ALPHA_META = "Alpha/Meta-ALP/ALP-META-Master-Plan.md"
ALPHA_COMMENT = "the Exec scaffold finished; Meta notes are in the Meta plan"
NOTE_BANNER = "Historical notes moved from the plans index"


def _git(root: Path, *argv: str) -> None:
    subprocess.run(["git", "-c", "core.autocrlf=false", *argv], cwd=str(root), check=True,
                   capture_output=True)


def _project(tmp_path, plans=None):
    """Byte-build Fixture B under `tmp_path/proj`, git-init and commit it.
    Returns `(cfg, plans_dir)`. `plans` replaces the Master Plan set."""
    _config, plans_dir, _index = build(tmp_path, legacy_index(B_LINES), plans or B_PLANS)
    root = tmp_path / "proj"
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-q", "-m", "fixture")
    cfg = InitConfig(project_name="e2e-plans", project_root=root, plugin_root=REAL_PLUGIN_ROOT,
                     plugin_version=TO)
    return cfg, plans_dir


def _pin(cfg, pinned: str) -> None:
    """Prepend plugin_root/plugin_version so `_run_upgrade()` has a pin to read."""
    config_path = cfg.project_root / "planwise" / "config.yaml"
    posix_root = str(cfg.plugin_root).replace("\\", "/")
    head = f'plugin_root: "{posix_root}"\nplugin_version: "{pinned}"\n'.encode()
    config_path.write_bytes(head + config_path.read_bytes())


def _tree(directory: Path) -> dict:
    return {p.relative_to(directory).as_posix(): p.read_bytes() for p in directory.rglob("*") if p.is_file()}


def _config(cfg) -> dict:
    return config_loader.load_config(Path(mig.__file__), config_path=cfg.project_root / "planwise" / "config.yaml")


def _run_init(cfg) -> None:
    old_argv = sys.argv[:]
    sys.argv = ["init_project.py", "--name", "e2e-init", "--project-root", str(cfg.project_root)]
    try:
        ip.main()
    finally:
        sys.argv = old_argv


def _row_paths(index_text: str) -> list:
    """The Path cell of every table row the generated index carries."""
    paths = []
    for line in index_text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if line.startswith("|") and len(cells) == 6 and cells[0] != "Abbrev" and set(cells[0]) != {"-"}:
            paths.append(cells[5])
    return paths


def _assert_migrated_on_disk(cfg, plans_dir, before, banner, pair, capsys):
    after = _tree(plans_dir)

    # 1. The banner shows `migrated`.
    assert "Plans index migration:" in banner
    assert "  migrated: " in banner and "generated from the Master Plans" in banner

    # 2. Backups: one byte-exact pre-image per file the run changed, under the pair's plans folder.
    changed = {rel for rel in before if after.get(rel) != before[rel]}
    assert {INDEX, ALPHA_EXEC} <= changed
    backups = _tree(cfg.project_root / "planwise" / "upgrade-backups" / pair / "plans")
    assert backups == {rel: before[rel] for rel in changed}

    # 3. One DISPOSITIONS row per backed-up file.
    disposition_log = cfg.project_root / "planwise" / "upgrade-backups" / pair / "DISPOSITIONS.md"
    rows = [ln for ln in disposition_log.read_bytes().decode("utf-8").splitlines() if "plans-backed-up:" in ln]
    assert len(rows) == len(backups)

    # 4. Each pre-image is a byte-exact prefix of its Master Plan.
    for rel in changed - {INDEX}:
        assert after[rel].startswith(before[rel]) and len(after[rel]) > len(before[rel]), rel

    # 5. The Alpha comment sits in the Exec child, after the banner. The Meta child is untouched.
    exec_text = after[ALPHA_EXEC].decode("utf-8")
    assert NOTE_BANNER in exec_text and ALPHA_COMMENT in exec_text
    assert exec_text.index(NOTE_BANNER) < exec_text.index(ALPHA_COMMENT)
    assert after[ALPHA_META] == before[ALPHA_META]

    # 6. No generated Path carries the `Plans/` prefix.
    paths = _row_paths(after[INDEX].decode("utf-8"))
    assert len(paths) >= 3 and not [p for p in paths if p.startswith("Plans/")]

    # 7. The generator `--check` exits 0 (in process).
    config = _config(cfg)
    assert gen.check_plans_index(config).exit_code == 0

    # 8. The ledger exists and accounts for every byte.
    ledger = (plans_dir / mig.LEDGER_FILENAME).read_bytes().decode("utf-8")
    assert "- Unaccounted: 0" in ledger and "- Mode: write" in ledger

    # 9. `--report --json` now reads `generated`.
    capsys.readouterr()
    assert mig.run(config, mig.build_parser().parse_args(["--report", "--json"])) == 0
    assert json.loads(capsys.readouterr().out)["shape"] == "generated"


def test_path1_run_upgrade_migrates_fixture_b_end_to_end(tmp_path, monkeypatch, capsys):
    cfg, plans_dir = _project(tmp_path)
    _pin(cfg, FROM)
    before = _tree(plans_dir)
    monkeypatch.setattr(artifact_upgrade, "INSTALLED_RULES", [])

    exit_code = artifact_upgrade._run_upgrade(cfg, lessons_reconcile=None)
    banner = capsys.readouterr().out

    assert exit_code == 0
    _assert_migrated_on_disk(cfg, plans_dir, before, banner, f"{FROM}-to-{TO}", capsys)

    # 10. A second run prints no plans banner and leaves the tree bytes identical.
    settled = _tree(plans_dir)
    backups = _tree(cfg.project_root / "planwise" / "upgrade-backups")
    assert artifact_upgrade._run_upgrade(cfg, lessons_reconcile=None) == 0
    assert "Plans index migration:" not in capsys.readouterr().out
    assert _tree(plans_dir) == settled
    assert _tree(cfg.project_root / "planwise" / "upgrade-backups") == backups


def test_path2_fresh_init_defers_fixture_b_and_the_seed_copy_spares_the_legacy_index(
    tmp_path, capsys,
):
    cfg, plans_dir = _project(tmp_path)
    before = _tree(plans_dir)
    assert before[INDEX].startswith(b"# Plans Index") and b"| ALP |" in before[INDEX]

    _run_init(cfg)
    banner = capsys.readouterr().out

    # The seed copy did not overwrite the legacy index, and plain init only detects it:
    # every file the fixture started with keeps its bytes, no backup is made, and the
    # Skipped section names /planwise upgrade as the step that migrates it.
    assert "Seed files installed:" in banner and "  + planwise/Plans/00-Index-Plans.md" not in banner
    assert "Plans index migration: DEFERRED (index and Master Plans left untouched)" in banner.splitlines()
    after = _tree(plans_dir)
    assert {name: after.get(name) for name in before} == before
    assert not (cfg.project_root / "planwise" / "upgrade-backups").exists()
    assert "Skipped (action required):" in banner
    assert "run /planwise upgrade" in banner.split("Skipped (action required):", 1)[1]

    # A second init defers again and still writes nothing.
    settled = _tree(plans_dir)
    _run_init(cfg)
    assert "Plans index migration: DEFERRED" in capsys.readouterr().out
    assert _tree(plans_dir) == settled


def test_refusal_variant_changes_nothing_keeps_the_exit_code_and_commits_the_pin(tmp_path, monkeypatch, capsys):
    """A Master Plan in the append set that is not valid UTF-8 refuses the plan before any write."""
    plans = dict(B_PLANS)
    plans[ALPHA_EXEC] = plans[ALPHA_EXEC] + b"\nBad byte: \xff\n"
    cfg, plans_dir = _project(tmp_path, plans)
    _pin(cfg, FROM)
    before = _tree(plans_dir)
    monkeypatch.setattr(artifact_upgrade, "INSTALLED_RULES", [])

    exit_code = artifact_upgrade._run_upgrade(cfg, lessons_reconcile=None)
    banner = capsys.readouterr().out

    assert exit_code == 0
    assert "Plans index migration: REFUSED (index and Master Plans left untouched)" in banner.splitlines()
    assert _tree(plans_dir) == before
    assert not (cfg.project_root / "planwise" / "upgrade-backups" / f"{FROM}-to-{TO}" / "plans").exists()
    assert f'plugin_version: "{TO}"' in (cfg.project_root / "planwise" / "config.yaml").read_text(encoding="utf-8")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
