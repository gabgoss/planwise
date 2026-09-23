"""Tests for migrate_backlog_index.py: the three-fixture refusal proof, plus
regression tests per safety finding. Fixtures live under tmp_path, never
under plugins/planwise/."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"
SCRIPT = SCRIPTS / "migrate_backlog_index.py"
GENERATOR = SCRIPTS / "generate_backlog_index.py"
sys.path.insert(0, str(SCRIPTS))
import generate_backlog_index as gen  # noqa: E402
import migrate_backlog_index as mig  # noqa: E402
import migrate_backlog_support as sup  # noqa: E402

NO_GIT = "--allow-untracked-tree"
FEATURE_TITLE = "Sample item needs love"
DUP_SENTENCE = "This extra detail duplicates content already present in the item file for dedup testing purposes."
NEW_SENTENCE = "This extra detail is brand new prose the item file has never mentioned anywhere at all today."
FEATURE_CELL = f"{FEATURE_TITLE}. {DUP_SENTENCE} {NEW_SENTENCE}"
SHORT_CELL = "Widgets frobnicate sprockets inside the gearbox"
AMBIG = "Alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima mike."
AMBIG_BODY = "Alpha bravo charlie delta echo foxtrot golf then something unrelated follows."
HEADER = "| ID | Feature | Priority | Status | Created | Blocks | Files |\n|---|---|---|---|---|---|---|\n"
FOOTER = "*Last Updated: 2024-01-01 — did something. Prior entry: 2023-12-01 — did something else.*\n"


def legacy_index(*cells, blocks="", extra=""):
    rows = "".join(f"| 001 | {c} | High | NOT_STARTED | 2024-01-01 | {blocks} | [001](001-Sample.md) |\n"
                   for c in (cells or (FEATURE_CELL,)))
    return f"## Backlog Items\n\n{HEADER}{rows}\n{FOOTER}{extra}"


LEGACY_INDEX = legacy_index()
UNRECOGNIZED_INDEX = ("## Backlog Items\n\n| ID | Feature | Priority | Status | Created | Blocks | Owner | Files |\n"
                      "|---|---|---|---|---|---|---|---|\n"
                      "| 001 | Some title | High | NOT_STARTED | 2024-01-01 |  | nobody | [001](001-Sample.md) |\n\n"
                      "*Last Updated: 2024-01-01 -- did something.*\n")
MIGRATED_INDEX = ("Generated: 2024-01-01\n\n| ID | Title | Priority | Status | Domain | Created | Blocks | Score | File |\n"
                  "|---|---|---|---|---|---|---|---|---|\n")
SOFT_DEPS_INDEX = LEGACY_INDEX.replace(
    "*Last Updated:", "## Dependencies\n\n| ID | Blocks |\n|---|---|\n| 001 | 002 |\n\n"
    "**Soft dependencies**\n\n- 001 relates loosely to 003\n\n---\n\n*Last Updated:")


def item_text(body=DUP_SENTENCE, nl="\n", status="NOT_STARTED", drop_key=None):
    fm = {"id": "001", "title": FEATURE_TITLE, "priority": "High", "status": status,
          "abbrev": "SMP", "created": "2024-01-01", "blocks": "[]"}
    lines = ["---"] + [f"{k}: {v}" for k, v in fm.items() if k != drop_key]
    return nl.join(lines + ["---", "", "# Sample Item", "", body, ""])

def _make_project(tmp_path, index_text, item=None, index_name="00-Index-Backlog.md"):
    planwise = tmp_path / "proj" / "planwise"
    backlog = planwise / "Backlog"
    (backlog / "Archive").mkdir(parents=True)
    (backlog / "001-Sample.md").write_text(item_text() if item is None else item, encoding="utf-8", newline="")
    (planwise / "config.yaml").write_text(
        f'project:\n  name: "test-project"\n  backlog_dir: "Backlog"\n'
        f'  index_files:\n    backlog: "{index_name}"\n', encoding="utf-8")
    index = backlog / index_name
    index.write_text(index_text, encoding="utf-8", newline="")
    return planwise / "config.yaml", index

def _item(index_path):
    return index_path.parent / "001-Sample.md"

def _changelog(index_path):
    return mig.artifact_paths(index_path)[0]

def _ledger(index_path):
    return mig.artifact_paths(index_path)[1]

def _snapshot(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*")
            if p.is_file() and ".git" not in p.parts}

def _run(config_path, *extra_args, script=SCRIPT):
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    return subprocess.run([sys.executable, str(script), "--config", str(config_path), *extra_args],
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=120, env=env)

def _run_inproc(monkeypatch, config_path, *extra_args):
    monkeypatch.setattr(sys, "argv", ["migrate_backlog_index.py", "--config", str(config_path), *extra_args])
    return mig.main()

def _git_commit(config_path):
    root = config_path.parent.parent
    subprocess.run(["git", "init", "-q"], cwd=str(root), check=True)
    subprocess.run(["git", "add", "-A"], cwd=str(root), check=True)
    subprocess.run(["git", "-c", "user.email=t@example.com", "-c", "user.name=t",
                    "commit", "-q", "-m", "init"], cwd=str(root), check=True)
    return root

def _crash_on(name):
    def replace(src, dst):
        if Path(dst).name == name:
            raise OSError("simulated crash")
        return os.replace(src, dst)
    return replace

# --- the original three-fixture refusal proof and write path ---

def test_recognized_legacy_dry_run_reports_plan_and_writes_nothing(tmp_path):
    config_path, _ = _make_project(tmp_path, LEGACY_INDEX)
    before = _snapshot(tmp_path)
    proc = _run(config_path, NO_GIT)
    assert proc.returncode == 1, proc.stderr + proc.stdout
    assert "DRY-RUN" in proc.stdout and "dedup" in proc.stdout
    assert _snapshot(tmp_path) == before

def test_three_fixtures_produce_three_distinct_outcomes(tmp_path):
    procs = {name: _run(_make_project(tmp_path / name, text)[0], NO_GIT)
             for name, text in (("legacy", LEGACY_INDEX), ("unrecognized", UNRECOGNIZED_INDEX),
                                ("migrated", MIGRATED_INDEX))}
    codes = {name: proc.returncode for name, proc in procs.items()}
    assert codes == {"legacy": 1, "unrecognized": 2, "migrated": 0}
    assert len(set(codes.values())) == 3
    assert "REFUSED" in procs["unrecognized"].stderr and "column" in procs["unrecognized"].stderr
    assert "CLEAN" in procs["migrated"].stdout

def test_write_extracts_changelog_dedups_and_writes_ledger(tmp_path):
    config_path, index_path = _make_project(tmp_path, LEGACY_INDEX)
    proc = _run(config_path, NO_GIT, "--write")
    assert proc.returncode == 0, proc.stderr + proc.stdout
    changelog_text = _changelog(index_path).read_text(encoding="utf-8")
    assert "did something" in changelog_text and "did something else" in changelog_text
    ledger = json.loads(_ledger(index_path).read_text(encoding="utf-8"))
    assert ledger["changelog"]["unaccounted"] == 0
    assert ledger["dedup"]["appended_bytes"] > 0 and ledger["dedup"]["deduplicated_bytes"] > 0
    index_text = index_path.read_text(encoding="utf-8")
    assert "moved to" in index_text and "Prior entry:" not in index_text
    item = _item(index_path).read_text(encoding="utf-8")
    assert item.count(NEW_SENTENCE) == 1 and item.count(DUP_SENTENCE) == 1

def test_dedup_unit_classification_is_pure_and_correct():
    index = sup.body_index(DUP_SENTENCE)
    high, low = sup.DEFAULT_HIGH, sup.DEFAULT_LOW
    assert sup.classify_unit(*sup.score_unit(DUP_SENTENCE, index), high, low) == "ALREADY-PRESENT"
    assert sup.classify_unit(*sup.score_unit(NEW_SENTENCE, index), high, low) == "MISSING"

# --- recognise-or-refuse covers everything regeneration would destroy ---

@pytest.mark.parametrize("index_text,item,expected", [
    (LEGACY_INDEX, item_text(status="IN_PROGRESS"), ["001", "Status", "NOT_STARTED", "IN_PROGRESS"]),
    (legacy_index(blocks="002"), None, ["001", "Blocks", "002"]),
    (LEGACY_INDEX, item_text(drop_key="created"), ["created", "generator"]),
])
def test_cell_disagreement_or_missing_key_is_refused_before_any_write(tmp_path, index_text, item, expected):
    config_path, _ = _make_project(tmp_path, index_text, item=item)
    before = _snapshot(tmp_path)
    proc = _run(config_path, NO_GIT, "--write")
    assert proc.returncode == 2, proc.stderr + proc.stdout
    assert all(fragment in proc.stderr for fragment in expected), proc.stderr
    assert _snapshot(tmp_path) == before

def test_short_feature_cell_differing_from_title_is_moved(tmp_path):
    config_path, index_path = _make_project(tmp_path, legacy_index(SHORT_CELL))
    proc = _run(config_path, NO_GIT, "--write")
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert _item(index_path).read_text(encoding="utf-8").count(SHORT_CELL) == 1

def test_short_feature_cell_equal_to_title_moves_nothing(tmp_path):
    proc = _run(_make_project(tmp_path, legacy_index(FEATURE_TITLE))[0], NO_GIT, "--json")
    assert proc.returncode == 1, proc.stderr + proc.stdout
    assert json.loads(proc.stdout)["dedup"]["units"] == 0

@pytest.mark.parametrize("index_text,fragment", [
    (legacy_index(extra="\n## Notes\n\nFree prose here.\n"), "## Notes"),
    (LEGACY_INDEX.replace("\n*Last Updated", "\nStray prose line.\n\n*Last Updated"), "text after the table"),
    ("# Backlog Index\n\nIntro prose the generator drops.\n\n" + LEGACY_INDEX, "line 3: preamble text"),
    (LEGACY_INDEX.replace("## Backlog Items\n\n", "## Backlog Items\n\nSome intro.\n\n"),
     "line 3: text between '## Backlog Items' and its table"),
    (SOFT_DEPS_INDEX, "Dependencies"),
])
def test_unrecognised_section_or_stray_text_is_refused(tmp_path, index_text, fragment):
    proc = _run(_make_project(tmp_path, index_text)[0], NO_GIT, "--write")
    assert proc.returncode == 2 and fragment in proc.stderr, proc.stderr + proc.stdout

def test_title_and_metadata_preamble_is_accepted(tmp_path):
    preamble = "# Backlog Index\n\n**Purpose:** Track work.\n**Last Updated:** 2024-01-01\n\n---\n\n"
    proc = _run(_make_project(tmp_path, preamble + LEGACY_INDEX)[0], NO_GIT)
    assert proc.returncode == 1, proc.stderr + proc.stdout

# --- atomic, resumable, and "already migrated" by state ---

def test_already_migrated_state_is_clean_and_rerun_appends_nothing(tmp_path):
    config_path, index_path = _make_project(tmp_path, LEGACY_INDEX)
    assert _run(config_path, NO_GIT, "--write").returncode == 0
    after_first = _snapshot(tmp_path)
    dry = _run(config_path, NO_GIT)
    assert dry.returncode == 0 and "CLEAN" in dry.stdout, dry.stderr + dry.stdout
    again = _run(config_path, NO_GIT, "--write")
    assert again.returncode == 0, again.stderr + again.stdout
    assert _snapshot(tmp_path) == after_first
    assert _item(index_path).read_text(encoding="utf-8").count(NEW_SENTENCE) == 1

def test_staging_failure_changes_nothing_on_disk(tmp_path, monkeypatch):
    config_path, _ = _make_project(tmp_path, LEGACY_INDEX)
    before, calls = _snapshot(tmp_path), []
    def failing_mkstemp(*args, **kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise OSError("simulated disk full")
        return tempfile.mkstemp(*args, **kwargs)
    monkeypatch.setattr(sup, "_mkstemp", failing_mkstemp)
    assert _run_inproc(monkeypatch, config_path, NO_GIT, "--write") == 1
    assert _snapshot(tmp_path) == before

def test_interrupted_replace_resumes_and_ledger_names_prior_run(tmp_path, monkeypatch):
    config_path, index_path = _make_project(tmp_path, LEGACY_INDEX)
    monkeypatch.setattr(sup, "_replace", _crash_on(index_path.name))
    assert _run_inproc(monkeypatch, config_path, NO_GIT, "--write") == 1
    assert _changelog(index_path).exists() and "Prior entry:" in index_path.read_text(encoding="utf-8")
    monkeypatch.undo()
    proc = _run(config_path, NO_GIT, "--write")
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert _item(index_path).read_text(encoding="utf-8").count(NEW_SENTENCE) == 1
    assert _changelog(index_path).read_text(encoding="utf-8").count("did something else") == 1
    assert not list(tmp_path.rglob("*.staged"))
    ledger = json.loads(_ledger(index_path).read_text(encoding="utf-8"))
    dedup, dest = ledger["dedup"], ledger["destinations"][0]
    assert (dedup["appended_by_prior_run_units"], dedup["deduplicated_units"], dedup["appended_units"]) == (1, 1, 0)
    assert dest["bytes_before_basis"].startswith("resumed") and "not recoverable" in dest["bytes_before_basis"]
    assert ledger["verification"] == {"verified": True, "misses": []}

def test_verify_written_checks_prior_run_units(tmp_path):
    _, index_path = _make_project(tmp_path, LEGACY_INDEX)
    _changelog(index_path).write_text("log\n", encoding="utf-8")
    plan = {"changelog": {"segments": []}, "index_text": mig.read_text(index_path),
            "dests": [{"path": _item(index_path), "append": [], "prior": [("001", "text never written")]}]}
    misses = mig.verify_written(plan, mig.artifact_paths(index_path), index_path)
    assert misses == ["row 001 unit 'text never written' is missing from 001-Sample.md"]

def test_foreign_changelog_from_older_run_is_refused(tmp_path):
    config_path, index_path = _make_project(tmp_path, LEGACY_INDEX)
    _changelog(index_path).write_text("unrelated content\n", encoding="utf-8")
    proc = _run(config_path, NO_GIT, "--write")
    assert proc.returncode == 2 and "already exists" in proc.stderr, proc.stderr + proc.stdout

def test_pointer_footer_with_prose_missing_is_refused_as_half_migrated(tmp_path):
    config_path, index_path = _make_project(tmp_path, LEGACY_INDEX)
    original_item = _item(index_path).read_bytes()
    assert _run(config_path, NO_GIT, "--write").returncode == 0
    _item(index_path).write_bytes(original_item)
    proc = _run(config_path, NO_GIT)
    assert proc.returncode == 2 and "half-migrated" in proc.stderr, proc.stderr + proc.stdout

# --- the tree state: fail closed, and resume through the dirty check ---

def test_unknown_git_state_refuses_without_override(tmp_path):
    config_path, _ = _make_project(tmp_path, LEGACY_INDEX)
    proc = _run(config_path)
    assert proc.returncode == 2, proc.stderr + proc.stdout
    assert "cannot determine" in proc.stderr and NO_GIT in proc.stderr
    allowed = _run(config_path, NO_GIT)
    assert allowed.returncode == 1 and "WARNING" in allowed.stderr, allowed.stderr + allowed.stdout

def test_dirty_working_tree_is_refused_without_force(tmp_path):
    config_path, index_path = _make_project(tmp_path, LEGACY_INDEX)
    _git_commit(config_path)
    clean = _run(config_path)
    assert clean.returncode == 1, clean.stderr + clean.stdout
    index_path.write_text(LEGACY_INDEX + "\n", encoding="utf-8")
    proc = _run(config_path)
    assert proc.returncode == 2 and "uncommitted" in proc.stderr.lower(), proc.stderr + proc.stdout
    forced = _run(config_path, "--force")
    assert forced.returncode == 1, forced.stderr + forced.stdout

@pytest.mark.parametrize("crash_target", ["index", "changelog"])
def test_interrupted_migration_resumes_on_real_git_repo_without_force(tmp_path, monkeypatch, crash_target):
    config_path, index_path = _make_project(tmp_path, LEGACY_INDEX)
    root = _git_commit(config_path)
    name = index_path.name if crash_target == "index" else _changelog(index_path).name
    monkeypatch.setattr(sup, "_replace", _crash_on(name))
    assert _run_inproc(monkeypatch, config_path, "--write") == 1
    monkeypatch.undo()
    unrelated = root / "planwise" / "unrelated.md"
    unrelated.write_text("someone else's edit\n", encoding="utf-8")
    blocked = _run(config_path, "--write")
    assert blocked.returncode == 2 and "unrelated.md" in blocked.stderr, blocked.stderr + blocked.stdout
    unrelated.unlink()
    resumed = _run(config_path, "--write")
    assert resumed.returncode == 0, resumed.stderr + resumed.stdout
    assert _item(index_path).read_text(encoding="utf-8").count(NEW_SENTENCE) == 1
    assert "moved to" in index_path.read_text(encoding="utf-8")

# --- changelog and ledger names survive a custom index name ---

def test_custom_index_name_changelog_is_skipped_by_generator(tmp_path):
    config_path, index_path = _make_project(tmp_path, LEGACY_INDEX, index_name="Backlog-Index.md")
    proc = _run(config_path, NO_GIT, "--write")
    assert proc.returncode == 0, proc.stderr + proc.stdout
    backlog = index_path.parent
    assert (_changelog(index_path).name, _ledger(index_path).name) == (
        "00-Backlog-Index-Changelog.md", "00-Backlog-Index-Migration-Ledger.json")
    scanned = [p.name for p in gen._iter_item_files(backlog, backlog / "Archive", index_path)]
    assert scanned == ["001-Sample.md"]
    generated = _run(config_path, "--write", script=GENERATOR)
    assert generated.returncode == 0, generated.stderr + generated.stdout
    checked = _run(config_path, "--check", script=GENERATOR)
    assert checked.returncode == 0, checked.stderr + checked.stdout
    assert _changelog(index_path).exists() and _ledger(index_path).exists()

def test_older_changelog_name_under_custom_index_is_refused(tmp_path):
    config_path, index_path = _make_project(tmp_path, LEGACY_INDEX, index_name="Backlog-Index.md")
    (index_path.parent / "Backlog-Index-Changelog.md").write_text("old\n", encoding="utf-8")
    proc = _run(config_path, NO_GIT)
    assert proc.returncode == 2 and "rename it to 00-Backlog-Index-Changelog.md" in proc.stderr, proc.stderr

# --- running dedup per destination; newline style and permission mode preserved ---

def test_two_rows_one_file_and_repeated_units_append_once(tmp_path):
    second = f"{FEATURE_TITLE}. {NEW_SENTENCE} {NEW_SENTENCE}"
    config_path, index_path = _make_project(tmp_path, legacy_index(FEATURE_CELL, second))
    proc = _run(config_path, NO_GIT, "--write")
    assert proc.returncode == 0, proc.stderr + proc.stdout
    item = _item(index_path).read_text(encoding="utf-8")
    assert item.count(NEW_SENTENCE) == 1 and item.count(DUP_SENTENCE) == 1

def test_crlf_item_file_stays_crlf(tmp_path):
    config_path, index_path = _make_project(tmp_path, LEGACY_INDEX, item=item_text(nl="\r\n"))
    assert _run(config_path, NO_GIT, "--write").returncode == 0
    data = _item(index_path).read_bytes()
    assert NEW_SENTENCE.encode() in data and data.count(b"\n") == data.count(b"\r\n")

def test_stage_all_preserves_target_mode_and_new_file_gets_umask_default(tmp_path):
    target, new = tmp_path / "target.md", tmp_path / "new.md"
    target.write_text("old\n", encoding="utf-8")
    os.chmod(target, 0o644)
    sup.replace_all(sup.stage_all([(target, "replaced\n"), (new, "created\n")]))
    assert target.read_text(encoding="utf-8") == "replaced\n" and new.read_text(encoding="utf-8") == "created\n"
    if os.name == "nt":
        pytest.skip("POSIX permission modes do not apply on Windows")
    assert target.stat().st_mode & 0o777 == 0o644
    assert new.stat().st_mode & 0o777 == sup.default_mode()

# --- the ledger is measured from disk and verified ---

def test_ledger_is_measured_from_disk(tmp_path):
    config_path, index_path = _make_project(tmp_path, LEGACY_INDEX)
    size_before = _item(index_path).stat().st_size
    assert _run(config_path, NO_GIT, "--write").returncode == 0
    ledger = json.loads(_ledger(index_path).read_text(encoding="utf-8"))
    dest = ledger["destinations"][0]
    assert (dest["bytes_before"], dest["bytes_before_basis"]) == (size_before, "pre-migration")
    assert dest["bytes_after"] == _item(index_path).stat().st_size
    assert dest["bytes_added"] == dest["bytes_after"] - size_before
    assert ledger["changelog"]["bytes_on_disk"] == _changelog(index_path).stat().st_size
    assert ledger["verification"] == {"verified": True, "misses": []}
    assert "discarded_bytes" not in ledger["dedup"]
    assert ledger["dedup"]["deduplicated_bytes"] == len(DUP_SENTENCE.encode())

def test_verification_miss_exits_1_naming_the_unit(tmp_path, monkeypatch, capsys):
    config_path, index_path = _make_project(tmp_path, LEGACY_INDEX)
    original = _item(index_path).read_bytes()
    def clobbering_replace(src, dst):
        os.replace(src, dst)
        if Path(dst).name == "001-Sample.md":
            Path(dst).write_bytes(original)
    monkeypatch.setattr(sup, "_replace", clobbering_replace)
    assert _run_inproc(monkeypatch, config_path, NO_GIT, "--write") == 1
    err = capsys.readouterr().err
    assert "row 001 unit" in err and NEW_SENTENCE[:40] in err
    assert json.loads(_ledger(index_path).read_text(encoding="utf-8"))["verification"]["verified"] is False

# --- window dedup, split overrides, and pure --json ---

def test_hard_wrapped_sentence_counts_as_already_present(tmp_path):
    wrapped = "This extra detail duplicates content\nalready present in the item file\nfor dedup testing purposes."
    proc = _run(_make_project(tmp_path, LEGACY_INDEX, item=item_text(body=wrapped))[0], NO_GIT, "--json")
    assert proc.returncode == 1, proc.stderr + proc.stdout
    dedup = json.loads(proc.stdout)["dedup"]
    assert (dedup["deduplicated_units"], dedup["appended_units"]) == (1, 1)

def test_force_never_appends_ambiguous_and_never_double_appends(tmp_path):
    item = item_text(body=AMBIG_BODY)
    assert sup.classify_unit(*sup.score_unit(AMBIG, sup.body_index(item)),
                             sup.DEFAULT_HIGH, sup.DEFAULT_LOW) == "AMBIGUOUS"
    config_path, index_path = _make_project(tmp_path, legacy_index(AMBIG), item=item)
    forced = _run(config_path, NO_GIT, "--force", "--write")
    assert forced.returncode == 2 and "--append-ambiguous" in forced.stderr, forced.stderr + forced.stdout
    for _ in range(2):
        proc = _run(config_path, NO_GIT, "--force", "--append-ambiguous", "--write")
        assert proc.returncode == 0, proc.stderr + proc.stdout
    assert _item(index_path).read_text(encoding="utf-8").count(AMBIG) == 1

def test_json_stdout_is_pure_json(tmp_path):
    config_path, _ = _make_project(tmp_path, LEGACY_INDEX)
    dry = _run(config_path, NO_GIT, "--json")
    assert dry.returncode == 1 and json.loads(dry.stdout)["mode"] == "dry-run"
    assert "DRY-RUN" in dry.stderr and "WARNING" in dry.stderr
    wrote = _run(config_path, NO_GIT, "--json", "--write")
    assert wrote.returncode == 0 and json.loads(wrote.stdout)["verification"]["verified"] is True, wrote.stderr
