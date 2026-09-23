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
WRAPPED_DUP = "This extra detail duplicates content\nalready present in the item file\nfor dedup testing purposes."
FEATURE_CELL = f"{FEATURE_TITLE}. {DUP_SENTENCE} {NEW_SENTENCE}"
SHORT_CELL = "Widgets frobnicate sprockets inside the gearbox"
AMBIG = "Alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima mike."
AMBIG_BODY = "Alpha bravo charlie delta echo foxtrot golf then something unrelated follows."
NOT_UNIT = "The legacy column should NOT be removed until every reader has migrated."
NOT_BODY = "The legacy column should be removed until every reader has migrated."
Q_UNIT = "Move the rollout of the new scoring model from Q2 to Q4 after the review."
Q_BODY = "Move the rollout of the new scoring model from Q2 to Q3 after the review."
HEADER = "| ID | Feature | Priority | Status | Created | Blocks | Files |\n|---|---|---|---|---|---|---|\n"
FOOTER = "*Last Updated: 2024-01-01 — did something. Prior entry: 2023-12-01 — did something else.*\n"
DEPS_OK = "## Dependencies\n\n| ID | Blocks |\n|---|---|\n| 001 | 002 |\n\n---\n\n"
SHARDS_OK = "## Shards\n\n| Range | File |\n|---|---|\n| 001-099 | [Index-Backlog-001-099.md](Archive/x.md) |\n\n"
DESIGN_LINK = "[design](Archive/design-notes.md)"


def legacy_index(*cells, blocks="", extra="", files="[001](001-Sample.md)", row_id="001"):
    rows = "".join(f"| {row_id} | {c} | High | NOT_STARTED | 2024-01-01 | {blocks} | {files} |\n"
                   for c in (cells or (FEATURE_CELL,)))
    return f"## Backlog Items\n\n{HEADER}{rows}\n{FOOTER}{extra}"

def before_footer(index_text, section):
    return index_text.replace("*Last Updated: 2024", section + "*Last Updated: 2024")

def item_text(body=DUP_SENTENCE, nl="\n", status="NOT_STARTED", drop_key=None, item_id="001", blocks="[]"):
    fm = {"id": item_id, "title": FEATURE_TITLE, "priority": "High", "status": status,
          "abbrev": "SMP", "created": "2024-01-01", "blocks": blocks}
    lines = ["---"] + [f"{k}: {v}" for k, v in fm.items() if k != drop_key]
    return nl.join(lines + ["---", "", "# Sample Item", "", body, ""])

LEGACY_INDEX = legacy_index()
UNRECOGNIZED_INDEX = ("## Backlog Items\n\n| ID | Feature | Priority | Status | Created | Blocks | Owner | Files |\n"
                      "|---|---|---|---|---|---|---|---|\n"
                      "| 001 | Some title | High | NOT_STARTED | 2024-01-01 |  | nobody | [001](001-Sample.md) |\n\n"
                      "*Last Updated: 2024-01-01 -- did something.*\n")
MIGRATED_INDEX = ("Generated: 2024-01-01\n\n| ID | Title | Priority | Status | Domain | Created | Blocks | Score | File |\n"
                  "|---|---|---|---|---|---|---|---|---|\n")
SECOND_ITEM = {"002-Other.md": item_text(body="Other item.", item_id="002")}
BLOCKS_002 = item_text(blocks="[002]")

def _make_project(tmp_path, index_text, item=None, index_name="00-Index-Backlog.md", extra=None):
    planwise = tmp_path / "proj" / "planwise"
    backlog = planwise / "Backlog"
    (backlog / "Archive").mkdir(parents=True)
    (backlog / "001-Sample.md").write_text(item_text() if item is None else item, encoding="utf-8", newline="")
    for name, content in (extra or {}).items():
        (backlog / name).write_text(content, encoding="utf-8", newline="")
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
    return json.loads(mig.artifact_paths(index_path)[1].read_text(encoding="utf-8"))

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

def _after_replace(name, action):
    def replace(src, dst):
        if Path(dst).name == name and action == "crash":
            raise OSError("simulated crash")
        os.replace(src, dst)
        if Path(dst).name == name and action != "crash":
            Path(dst).write_bytes(action)
    return replace

def test_three_fixtures_produce_three_distinct_outcomes(tmp_path):
    procs = {name: _run(_make_project(tmp_path / name, text)[0], NO_GIT)
             for name, text in (("legacy", LEGACY_INDEX), ("unrecognized", UNRECOGNIZED_INDEX),
                                ("migrated", MIGRATED_INDEX))}
    codes = {name: proc.returncode for name, proc in procs.items()}
    assert codes == {"legacy": 1, "unrecognized": 2, "migrated": 0} and len(set(codes.values())) == 3
    assert "REFUSED" in procs["unrecognized"].stderr and "column" in procs["unrecognized"].stderr
    assert "CLEAN" in procs["migrated"].stdout and "DRY-RUN" in procs["legacy"].stdout

REFUSALS = [
    ("status", LEGACY_INDEX, item_text(status="IN_PROGRESS"), {}, (), ["001", "Status", "IN_PROGRESS"]),
    ("blocks", legacy_index(blocks="002"), None, {}, (), ["001", "Blocks", "002"]),
    ("blocks-prose", legacy_index(blocks="002 (soft)"), BLOCKS_002, SECOND_ITEM, (), ["other than ids"]),
    ("missing-key", LEGACY_INDEX, item_text(drop_key="created"), {}, (), ["created", "generator"]),
    ("section", legacy_index(extra="\n## Notes\n\nFree prose.\n"), None, {}, (), ["## Notes"]),
    ("after-table", LEGACY_INDEX.replace("\n*Last", "\nStray prose.\n\n*Last"), None, {}, (), ["after the table"]),
    ("preamble", "# Backlog\n\nIntro prose.\n\n" + LEGACY_INDEX, None, {}, (), ["line 3: preamble text"]),
    ("heading-gap", LEGACY_INDEX.replace("Items\n\n", "Items\n\nSome intro.\n\n"), None, {}, (),
     ["line 3: text between '## Backlog Items' and its table"]),
    ("deps-soft", before_footer(LEGACY_INDEX, DEPS_OK.replace("---", "**Soft dependencies**\n\n- 001 relates to 003")),
     None, {}, (), ["text under '## Dependencies'", "Soft dependencies"]),
    ("deps-prior-entry", before_footer(LEGACY_INDEX, DEPS_OK + "*Prior entry: 2023-11-01 — older.*\n\n"),
     None, {}, (), ["text under '## Dependencies'", "Prior entry"]),
    ("deps-to-eof", before_footer(legacy_index(blocks="002"), DEPS_OK) + "\nTrailing prose at EOF.\n", BLOCKS_002,
     SECOND_ITEM, (), ["text under '## Dependencies'", "Trailing prose at EOF"]),
    ("deps-edge", before_footer(LEGACY_INDEX, DEPS_OK), None, SECOND_ITEM, (), ["001 blocks 002"]),
    ("shards-row", before_footer(LEGACY_INDEX, SHARDS_OK.replace("x.md)", "x.md) and notes")), None, {}, (),
     ["'## Shards' row"]),
    ("files-prose", legacy_index(files="[001](001-Sample.md) plus notes"), None, {}, (), ["Files cell carries text"]),
    ("empty-id", legacy_index(row_id=""), None, {}, (), ["empty ID cell"]),
    ("foreign-changelog", LEGACY_INDEX, None, {"00-Index-Backlog-Changelog.md": "other\n"}, (), ["already exists"]),
    ("ambiguous-under-force", legacy_index(AMBIG), item_text(body=AMBIG_BODY), {}, (), ["--append-ambiguous"]),
    ("reviewer-not", legacy_index(NOT_UNIT), item_text(body=NOT_BODY), {}, (), ["ambiguous", "should NOT"]),
    ("reviewer-quarter", legacy_index(Q_UNIT), item_text(body=Q_BODY), {}, (), ["ambiguous", "Q4"]),
    ("thresholds-order", LEGACY_INDEX, None, {}, ("--thresholds", "0.3,0.5"), ["thresholds"]),
    ("thresholds-range", LEGACY_INDEX, None, {}, ("--thresholds", "1.5,0.2"), ["thresholds"]),
    ("thresholds-negative", LEGACY_INDEX, None, {}, ("--thresholds", "0.5,-0.1"), ["thresholds"]),
]

@pytest.mark.parametrize("index_text,item,extra,args,fragments", [pytest.param(*r[1:], id=r[0]) for r in REFUSALS])
def test_refused_before_any_write_even_under_force(tmp_path, index_text, item, extra, args, fragments):
    config_path, _ = _make_project(tmp_path, index_text, item=item, extra=extra)
    before = _snapshot(tmp_path)
    proc = _run(config_path, NO_GIT, "--force", "--write", *args)
    assert proc.returncode == 2, proc.stderr + proc.stdout
    assert all(fragment in proc.stderr for fragment in fragments), proc.stderr
    assert _snapshot(tmp_path) == before

@pytest.mark.parametrize("index_text,item,extra", [
    ("# Backlog Index\n\n**Purpose:** Track work.\n**Last Updated:** 2024-01-01\n\n---\n\n" + LEGACY_INDEX, None, {}),
    (before_footer(legacy_index(blocks="002"), SHARDS_OK + DEPS_OK), BLOCKS_002, SECOND_ITEM),
], ids=["title-and-metadata", "shards-and-deps-in-frontmatter"])
def test_recognised_shapes_dry_run_and_write_nothing(tmp_path, index_text, item, extra):
    config_path, _ = _make_project(tmp_path, index_text, item=item, extra=extra)
    before = _snapshot(tmp_path)
    proc = _run(config_path, NO_GIT)
    assert proc.returncode == 1 and "dedup" in proc.stdout, proc.stderr + proc.stdout
    assert _snapshot(tmp_path) == before

def test_older_changelog_name_under_custom_index_is_refused(tmp_path):
    extra = {"Backlog-Index-Changelog.md": "old\n"}
    config_path, _ = _make_project(tmp_path, LEGACY_INDEX, index_name="Backlog-Index.md", extra=extra)
    proc = _run(config_path, NO_GIT)
    assert proc.returncode == 2 and "rename it to 00-Backlog-Index-Changelog.md" in proc.stderr, proc.stderr

def test_write_extracts_changelog_dedups_and_writes_ledger(tmp_path):
    config_path, index_path = _make_project(tmp_path, LEGACY_INDEX)
    proc = _run(config_path, NO_GIT, "--write")
    assert proc.returncode == 0, proc.stderr + proc.stdout
    changelog_text = _changelog(index_path).read_text(encoding="utf-8")
    assert "did something" in changelog_text and "did something else" in changelog_text
    ledger = _ledger(index_path)
    assert (ledger["changelog"]["unaccounted"], ledger["changelog"]["unaccounted_basis"]) == (0, "changelog on disk")
    assert ledger["dedup"]["appended_bytes"] > 0 and ledger["dedup"]["deduplicated_bytes"] > 0
    index_text = index_path.read_text(encoding="utf-8")
    assert "moved to" in index_text and "Prior entry:" not in index_text
    item = _item(index_path).read_text(encoding="utf-8")
    assert item.count(NEW_SENTENCE) == 1 and item.count(DUP_SENTENCE) == 1

def test_only_an_exact_match_is_already_present():
    high, low = sup.DEFAULT_HIGH, sup.DEFAULT_LOW
    for unit, body in ((DUP_SENTENCE, DUP_SENTENCE), (DUP_SENTENCE, WRAPPED_DUP), ("**Bold** words.", "bold words.")):
        assert sup.classify_unit(*sup.score_unit(unit, sup.body_index(body)), high, low) == "ALREADY-PRESENT"
    for unit, body in ((NOT_UNIT, NOT_BODY), (Q_UNIT, Q_BODY)):
        exact, score, window = sup.score_unit(unit, sup.body_index(body))
        assert not exact and max(score, window) >= high  # the old rule called these ALREADY-PRESENT
        assert sup.classify_unit(exact, score, window, high, low) == "AMBIGUOUS"
    assert sup.classify_unit(*sup.score_unit(NEW_SENTENCE, sup.body_index(DUP_SENTENCE)), high, low) == "MISSING"

def test_short_feature_cell_differing_from_title_is_moved_and_equal_title_is_not(tmp_path):
    config_path, index_path = _make_project(tmp_path / "a", legacy_index(SHORT_CELL))
    assert _run(config_path, NO_GIT, "--write").returncode == 0
    assert _item(index_path).read_text(encoding="utf-8").count(SHORT_CELL) == 1
    proc = _run(_make_project(tmp_path / "b", legacy_index(FEATURE_TITLE))[0], NO_GIT, "--json")
    assert proc.returncode == 1 and json.loads(proc.stdout)["dedup"]["units"] == 0, proc.stderr

@pytest.mark.parametrize("body", [DUP_SENTENCE, f"{DUP_SENTENCE}\n\nSee [design notes](Archive/design-notes.md)."])
def test_extra_files_links_are_carried_once(tmp_path, body):
    files = f"[001](001-Sample.md), {DESIGN_LINK}"
    config_path, index_path = _make_project(tmp_path, legacy_index(files=files), item=item_text(body=body))
    for _ in range(2):
        proc = _run(config_path, NO_GIT, "--write")
        assert proc.returncode == 0, proc.stderr + proc.stdout
    item = _item(index_path).read_text(encoding="utf-8")
    assert item.count("(Archive/design-notes.md)") == 1 and (DESIGN_LINK in item) == (body == DUP_SENTENCE)

def test_two_rows_one_file_and_repeated_units_append_once(tmp_path):
    second = f"{FEATURE_TITLE}. {NEW_SENTENCE} {NEW_SENTENCE}"
    config_path, index_path = _make_project(tmp_path, legacy_index(FEATURE_CELL, second))
    proc = _run(config_path, NO_GIT, "--write")
    assert proc.returncode == 0, proc.stderr + proc.stdout
    item = _item(index_path).read_text(encoding="utf-8")
    assert item.count(NEW_SENTENCE) == 1 and item.count(DUP_SENTENCE) == 1

def test_append_ambiguous_never_double_appends(tmp_path):
    config_path, index_path = _make_project(tmp_path, legacy_index(AMBIG), item=item_text(body=AMBIG_BODY))
    for _ in range(2):
        proc = _run(config_path, NO_GIT, "--force", "--append-ambiguous", "--write")
        assert proc.returncode == 0, proc.stderr + proc.stdout
    assert _item(index_path).read_text(encoding="utf-8").count(AMBIG) == 1

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
    assert target.stat().st_mode & 0o777 == 0o644 and new.stat().st_mode & 0o777 == sup.default_mode()

def test_already_migrated_state_is_clean_and_rerun_appends_nothing(tmp_path):
    config_path, index_path = _make_project(tmp_path, LEGACY_INDEX)
    assert _run(config_path, NO_GIT, "--write").returncode == 0
    after_first = _snapshot(tmp_path)
    dry = _run(config_path, NO_GIT)
    assert dry.returncode == 0 and "CLEAN" in dry.stdout, dry.stderr + dry.stdout
    assert _run(config_path, NO_GIT, "--write").returncode == 0
    assert _snapshot(tmp_path) == after_first

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
    monkeypatch.setattr(sup, "_replace", _after_replace(index_path.name, "crash"))
    assert _run_inproc(monkeypatch, config_path, NO_GIT, "--write") == 1
    assert _changelog(index_path).exists() and "Prior entry:" in index_path.read_text(encoding="utf-8")
    monkeypatch.undo()
    proc = _run(config_path, NO_GIT, "--write")
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert _item(index_path).read_text(encoding="utf-8").count(NEW_SENTENCE) == 1
    assert _changelog(index_path).read_text(encoding="utf-8").count("did something else") == 1
    assert not list(tmp_path.rglob("*.staged"))
    ledger = _ledger(index_path)
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

def test_pointer_footer_with_prose_missing_is_refused_as_half_migrated(tmp_path):
    config_path, index_path = _make_project(tmp_path, LEGACY_INDEX)
    original_item = _item(index_path).read_bytes()
    assert _run(config_path, NO_GIT, "--write").returncode == 0
    _item(index_path).write_bytes(original_item)
    proc = _run(config_path, NO_GIT)
    assert proc.returncode == 2 and "half-migrated" in proc.stderr, proc.stderr + proc.stdout

def test_unknown_git_state_refuses_without_override(tmp_path):
    config_path, _ = _make_project(tmp_path, LEGACY_INDEX)
    proc = _run(config_path)
    assert proc.returncode == 2 and "cannot determine" in proc.stderr and NO_GIT in proc.stderr, proc.stderr
    allowed = _run(config_path, NO_GIT)
    assert allowed.returncode == 1 and "WARNING" in allowed.stderr, allowed.stderr + allowed.stdout

def test_git_ignored_backlog_is_an_unknown_tree_state(tmp_path):
    config_path, _ = _make_project(tmp_path, LEGACY_INDEX)
    (config_path.parent.parent / ".gitignore").write_text("planwise/Backlog/\n", encoding="utf-8")
    _git_commit(config_path)
    proc = _run(config_path)
    assert proc.returncode == 2 and "ignores" in proc.stderr and NO_GIT in proc.stderr, proc.stderr + proc.stdout
    assert _run(config_path, NO_GIT).returncode == 1

def test_dirty_working_tree_is_refused_without_force(tmp_path):
    config_path, index_path = _make_project(tmp_path, LEGACY_INDEX)
    _git_commit(config_path)
    assert _run(config_path).returncode == 1
    index_path.write_text(LEGACY_INDEX + "\n", encoding="utf-8")
    proc = _run(config_path)
    assert proc.returncode == 2 and "uncommitted" in proc.stderr.lower(), proc.stderr + proc.stdout
    assert _run(config_path, "--force").returncode == 1

@pytest.mark.parametrize("crash_target", ["index", "changelog"])
def test_interrupted_migration_resumes_on_real_git_repo_without_force(tmp_path, monkeypatch, crash_target):
    config_path, index_path = _make_project(tmp_path, LEGACY_INDEX)
    root = _git_commit(config_path)
    name = index_path.name if crash_target == "index" else _changelog(index_path).name
    monkeypatch.setattr(sup, "_replace", _after_replace(name, "crash"))
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

def test_custom_index_name_changelog_is_skipped_by_generator(tmp_path):
    config_path, index_path = _make_project(tmp_path, LEGACY_INDEX, index_name="Backlog-Index.md")
    proc = _run(config_path, NO_GIT, "--write")
    assert proc.returncode == 0, proc.stderr + proc.stdout
    backlog = index_path.parent
    assert (_changelog(index_path).name, mig.artifact_paths(index_path)[1].name) == (
        "00-Backlog-Index-Changelog.md", "00-Backlog-Index-Migration-Ledger.json")
    assert [p.name for p in gen._iter_item_files(backlog, backlog / "Archive", index_path)] == ["001-Sample.md"]
    for mode in ("--write", "--check"):
        generated = _run(config_path, mode, script=GENERATOR)
        assert generated.returncode == 0, mode + generated.stderr + generated.stdout
    assert _changelog(index_path).exists() and mig.artifact_paths(index_path)[1].exists()

def test_ledger_is_measured_from_disk(tmp_path):
    config_path, index_path = _make_project(tmp_path, LEGACY_INDEX)
    size_before = _item(index_path).stat().st_size
    assert _run(config_path, NO_GIT, "--write").returncode == 0
    ledger = _ledger(index_path)
    dest, size_after = ledger["destinations"][0], _item(index_path).stat().st_size
    assert (dest["bytes_before"], dest["bytes_before_basis"], dest["bytes_after"], dest["bytes_added"]) == (
        size_before, "pre-migration", size_after, size_after - size_before)
    assert ledger["changelog"]["bytes_on_disk"] == _changelog(index_path).stat().st_size
    assert ledger["verification"] == {"verified": True, "misses": []}
    assert "discarded_bytes" not in ledger["dedup"]
    assert ledger["dedup"]["deduplicated_bytes"] == len(DUP_SENTENCE.encode())

def test_verification_miss_exits_1_naming_the_unit(tmp_path, monkeypatch, capsys):
    config_path, index_path = _make_project(tmp_path, LEGACY_INDEX)
    monkeypatch.setattr(sup, "_replace", _after_replace("001-Sample.md", _item(index_path).read_bytes()))
    assert _run_inproc(monkeypatch, config_path, NO_GIT, "--write") == 1
    err = capsys.readouterr().err
    assert "row 001 unit" in err and NEW_SENTENCE[:40] in err
    assert _ledger(index_path)["verification"]["verified"] is False

def test_unaccounted_is_measured_from_the_changelog_on_disk(tmp_path, monkeypatch):
    config_path, index_path = _make_project(tmp_path, LEGACY_INDEX)
    monkeypatch.setattr(sup, "_replace", _after_replace(_changelog(index_path).name, b"truncated\n"))
    assert _run_inproc(monkeypatch, config_path, NO_GIT, "--write") == 1
    log = _ledger(index_path)["changelog"]
    assert log["unaccounted_basis"] == "changelog on disk"
    assert log["unaccounted"] == log["entry_content_bytes"] > 0

def test_json_stdout_is_pure_json(tmp_path):
    config_path, _ = _make_project(tmp_path, LEGACY_INDEX)
    dry = _run(config_path, NO_GIT, "--json")
    assert dry.returncode == 1 and json.loads(dry.stdout)["mode"] == "dry-run"
    assert "DRY-RUN" in dry.stderr and "WARNING" in dry.stderr
    wrote = _run(config_path, NO_GIT, "--json", "--write")
    assert wrote.returncode == 0 and json.loads(wrote.stdout)["verification"]["verified"] is True, wrote.stderr
