"""End-to-end tests for the backlog index retrofit.

`migrate_backlog_if_legacy` runs in-process over a legacy fixture that carries
every repair class at once: a 7-column header with Created and Blocks, a
Feature cell with prose beyond the title, a `## Dependencies` edge, a
soft-dependency bullet under a bold heading, a three-entry footer, and item
files with a full, a partial and no frontmatter block. The fixture is
committed to git, so a backfilled `created:` has a git source, and then one
item file is edited, so the tree is dirty.

Assertions 1-11 are labelled where they are made. Assertion 10 has two halves:
entries that total over budget split into parts, and one entry over budget
alone is refused by name. Assertion 9, the budget
sweep, runs after every call that writes a backlog index file: the hub and
its overflow leaves stay within `HUB_TOKEN_BUDGET`, and every Archive shard
and changelog part stays within `READ_TOKEN_WARN`. Fixtures are written as
bytes under tmp_path, never under plugins/planwise/.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import backlog_index_budget as budget
import backlog_migration as bm
import config_loader
import generate_backlog_index as gen
import migrate_backlog_index as mig
import migrate_backlog_support as sup
from config_gen import InitConfig
from read_limits import READ_TOKEN_WARN

FROM, TO = "1.0.5.1", "1.0.5.2"
INDEX = "00-Index-Backlog.md"
CHANGELOG = "00-Changelog-Backlog.md"
HEADER_ONLY = f"[← {INDEX}]({INDEX})\n"
CONFIG = ('project:\n  name: "e2e-project"\n  backlog_dir: "Backlog"\n  index_files:\n'
          f'    backlog: "{INDEX}"\nabbreviations:\n  SMP: Sample work\n')
FIRST, SECOND, THIRD = "ITEM-001-SMP-First.md", "ITEM-002-SMP-Second.md", "ITEM-003-SMP-Third.md"
TITLE1, TITLE2, TITLE3 = "First item complete", "Second item partial block", "Third item without frontmatter"
EXTRA2 = ("The parser rejects nested tables without a clear message.",
          "Operators need a remedy printed beside every rejection.")
BULLET = "- 003 relates to 001 (shared parser)"
ENTRIES = ("2024-03-01 — added the third item.", "2024-02-01 — added the second item.",
           "2024-01-01 — created the backlog.")
FIRST_TEXT = ("---\nid: 001\ntitle: \"First item complete\"\npriority: High\nstatus: COMPLETE\nabbrev: SMP\n"
              "created: 2024-01-01\nblocks: []\n---\n\n# First\n\nFirst body.\n")
SECOND_TEXT = ("---\nid: 002\ntitle: \"Second item partial block\"\npriority: Medium\nstatus: NOT_STARTED\n"
               "abbrev: SMP\n---\n\n# Second\n\nSecond body.\n")
THIRD_TEXT = "# Third\n\nThird body, with no frontmatter at all.\n"
DEPS_HEADING = "## Dependency Notes (migrated from the backlog index)"
# Row 003's Created cell. Filled, the cell is the backfill source. Empty, the cell supplies no
# value, so the backfill takes the file's git add date and the row check raises no disagreement.
CREATED3 = "2024-03-01"


def footer(entries=ENTRIES) -> str:
    return "*Last Updated: " + " Prior entry: ".join(entries) + "*"


def legacy_index(entries=ENTRIES, bullet=BULLET, created3=CREATED3) -> str:
    rows = (f"| 001 | {TITLE1} | High | COMPLETE | 2024-01-01 | 002 | [001]({FIRST}) |\n"
            f"| 002 | {TITLE2}. {EXTRA2[0]} {EXTRA2[1]} | Medium | NOT_STARTED | 2024-02-01 |  | [002]({SECOND}) |\n"
            f"| 003 | {TITLE3} | Low | NOT_STARTED | {created3} |  | [003]({THIRD}) |\n")
    return ("# Backlog Index\n\n## Backlog Items\n\n"
            "| ID | Feature | Priority | Status | Created | Blocks | Files |\n|---|---|---|---|---|---|---|\n"
            f"{rows}\n## Dependencies\n\n| ID | Blocks |\n|---|---|\n| 001 | 002 |\n\n"
            f"**Soft dependencies**\n\n{bullet}\n\n---\n\n{footer(entries)}\n")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def _git(root: Path, *argv: str) -> str:
    return subprocess.run(["git", "-c", "core.autocrlf=false", *argv], cwd=str(root), check=True,
                          capture_output=True, text=True).stdout


def _project(tmp_path, index_text=None):
    """Write the legacy fixture, commit it, then edit one item so the tree is dirty."""
    root = tmp_path / "proj"
    backlog = root / "planwise" / "Backlog"
    _write(root / "planwise" / "config.yaml", CONFIG)
    _write(backlog / INDEX, legacy_index() if index_text is None else index_text)
    _write(backlog / CHANGELOG, HEADER_ONLY)
    _write(backlog / FIRST, FIRST_TEXT)
    _write(backlog / SECOND, SECOND_TEXT)
    _write(backlog / THIRD, THIRD_TEXT)
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-q", "-m", "fixture")
    _write(backlog / FIRST, FIRST_TEXT + "\nEdited after the commit, so the tree is dirty.\n")
    cfg = InitConfig(project_name="e2e-project", project_root=root, plugin_root=SCRIPTS.parent)
    return cfg, backlog


def _snapshot(root: Path) -> dict:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*")
            if p.is_file() and ".git" not in p.parts}


def _config(cfg) -> dict:
    return config_loader.load_config(Path(bm.__file__), config_path=cfg.project_root / "planwise" / "config.yaml")


def _backups(cfg, pair=f"{FROM}-to-{TO}") -> Path:
    return cfg.project_root / "planwise" / "upgrade-backups" / pair


def _changelog_files(backlog: Path) -> list:
    pattern = sup.changelog_part_pattern(gen._index_naming(backlog / INDEX))
    return [backlog / CHANGELOG] + sorted(p for p in backlog.iterdir() if pattern.match(p.name))


def _frontmatter_lines(text: str) -> list:
    lines = text.replace("\r\n", "\n").split("\n")
    end = lines.index("---", 1)
    return lines[1:end]


def budget_sweep(cfg) -> list:
    """Assertion 9: measure every hub, overflow-leaf, Archive-shard and changelog file on disk
    with the generator's own `_measure`, on `\\n`-normalised text. Returns (name, tokens, limit)."""
    config = _config(cfg)
    index_path, backlog, archive = config["_index_path"], config["_backlog_dir"], config["_archive_dir"]
    index_files = gen._list_disk_generated_files(backlog, archive, gen._index_naming(index_path))
    measured, over = [], []
    for path in [*index_files, *_changelog_files(backlog)]:
        in_archive = Path(archive).resolve() in Path(path).resolve().parents
        is_changelog = Path(path).name.startswith("00-Changelog-")
        limit = READ_TOKEN_WARN if (in_archive or is_changelog) else budget.HUB_TOKEN_BUDGET
        tokens = budget._measure(mig.read_text(path).replace("\r\n", "\n"))[1]
        measured.append((Path(path).name, tokens, limit))
        if tokens > limit:
            over.append(f"{Path(path).name}: {tokens} tokens > {limit}")
    assert len(measured) >= 3, f"assertion 9: the budget sweep measured only {measured}; fewer than 3 is a FAIL"
    assert not over, "assertion 9: over budget -- " + "; ".join(over)
    return measured


def _check_exits(cfg) -> tuple:
    config = _config(cfg)
    index_path = config["_index_path"]
    in_process = gen._cmd_check(config["_backlog_dir"], config["_archive_dir"], index_path,
                                gen._index_naming(index_path), config, json_out=False)
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    proc = subprocess.run([sys.executable, str(SCRIPTS / "generate_backlog_index.py"), "--config",
                           str(cfg.project_root / "planwise" / "config.yaml"), "--check"],
                          capture_output=True, text=True, env=env, check=False)
    return in_process, proc.returncode, proc.stdout + proc.stderr


@pytest.mark.parametrize("created3", [CREATED3, ""], ids=["created-cell-filled", "created-cell-empty"])
def test_legacy_fixture_migrates_end_to_end(tmp_path, capsys, created3):
    cfg, backlog = _project(tmp_path, legacy_index(created3=created3))
    original_index = (backlog / INDEX).read_bytes()
    before = _snapshot(backlog)
    added = _git(cfg.project_root, "log", "--diff-filter=A", "--format=%as", "--",
                 f"planwise/Backlog/{THIRD}").split()

    report = bm.migrate_backlog_if_legacy(cfg, FROM, TO)
    bm._emit_backlog_migration_banner(report)
    banner = capsys.readouterr().out

    # Assertion 1: state, shape and shard.
    assert report.state == "migrated", report.detail
    hub = mig.read_text(backlog / INDEX)
    assert sup.classify_shape(hub)[0] == "migrated"
    assert "## Shards" in hub
    shards = sorted((backlog / "Archive").glob("*.md"))
    assert shards, "assertion 1: no Archive shard was written"
    # The migrated banner's own line AND the shape on disk: the shared prefix alone
    # does not tell a migrated run from an ERROR, REFUSED or FAILED one.
    assert "generator --check:      clean" in banner, banner
    assert report.git_dirty is True

    # Assertion 2: --check exits 0 in-process and through a subprocess.
    in_process, sub_rc, sub_out = _check_exits(cfg)
    assert (in_process, sub_rc) == (0, 0), sub_out

    # Assertion 3: every footer segment is in the changelog; the ledger accounts for every byte.
    log = sup.joined_entries([mig.read_text(p) for p in _changelog_files(backlog)])
    segments = sup.extract_changelog(original_index)["segments"]
    assert len(segments) == 3 and all(s.decode("utf-8") in log for s in segments)
    ledger = json.loads(mig.read_text(report.ledger_path))
    assert ledger["changelog"]["unaccounted"] == 0

    # Assertion 4: the four item-file facts.
    first, second, third = (mig.read_text(backlog / n) for n in (FIRST, SECOND, THIRD))
    assert "blocks: [002]" in _frontmatter_lines(first)
    third_fm = _frontmatter_lines(third)
    assert "id: 003" in third_fm and f'title: "{TITLE3}"' in third_fm
    # `created` comes from the Created cell when it holds a date, else from the git add date.
    expected_created = created3 or (added[-1] if added else "no git add date")
    assert f"created: {expected_created}" in third_fm, (added, third_fm)
    assert DEPS_HEADING in third and third.index(BULLET) > third.index(DEPS_HEADING)
    old_fm = _frontmatter_lines(SECOND_TEXT)
    new_fm = _frontmatter_lines(second)
    assert [line for line in new_fm if line not in old_fm] == ["created: 2024-02-01", "blocks: []"]
    assert all(line in new_fm for line in old_fm)
    notes = second[second.index(sup.NOTES_HEADING):]
    assert EXTRA2[0] in notes and EXTRA2[1] in notes

    # Assertion 5: backups byte-equal to the pre-run snapshot; one DISPOSITIONS row per written file.
    backups = _backups(cfg) / "backlog"
    for rel in (INDEX, CHANGELOG, FIRST, SECOND, THIRD):
        assert (backups / rel).read_bytes() == before[rel], rel
    rows = [r for r in (_backups(cfg) / "DISPOSITIONS.md").read_text(encoding="utf-8").splitlines()
            if "backlog-migrated" in r]
    assert len(rows) == len(report.written) == len(set(report.written))
    for written in report.written:
        assert sum(Path(written).name in r for r in rows) >= 1, written

    # Assertion 6: the ledger carries the new sections and verified itself from disk.
    for key in ("backfill", "edges", "dependency_notes", "reconcile"):
        assert key in ledger, key
    assert ledger["verification"]["verified"] is True
    assert {b["path"].replace("\\", "/").rsplit("/", 1)[1] for b in ledger["backfill"]} == {SECOND, THIRD}
    assert ledger["edges"] == [{"src": "001", "dst": "002"}]
    third_source = [b["created_source"] for b in ledger["backfill"] if b["path"].endswith(THIRD)]
    assert third_source == ["index" if created3 else "git"], third_source

    # Assertion 9: every backlog index file the call wrote is within its budget.
    budget_sweep(cfg)

    # Assertion 7: a same-pair re-run on the migrated index is silent, keeps the first
    # pre-images byte-equal, and leaves the whole tree byte-identical, backups included.
    after = _snapshot(cfg.project_root)
    again = bm.migrate_backlog_if_legacy(cfg, FROM, TO)
    assert again.state == "generated", again.detail
    assert _snapshot(cfg.project_root) == after
    for rel in (INDEX, CHANGELOG, FIRST, SECOND, THIRD):
        assert (backups / rel).read_bytes() == before[rel], rel
    assert f"]({CHANGELOG})" in hub  # the generated hub keeps its pointer to the changelog


def test_pointer_footer_index_resumes_at_the_generator(tmp_path, monkeypatch):
    # Assertion 7, resume form: the migrator wrote the pointer footer but the generator failed.
    # The next call regenerates only (state `migrated`); the call after it is silent.
    cfg, backlog = _project(tmp_path)
    with monkeypatch.context() as m:
        m.setattr(gen, "_cmd_write", lambda *a, **k: 1)
        assert bm.migrate_backlog_if_legacy(cfg, FROM, TO).state == "write_failed"
    index = mig.read_text(backlog / INDEX)
    assert sup.classify_shape(index)[0] == "legacy" and sup.POINTER_RE.match(sup.FOOTER_TEXT_RE.search(index)[0])
    resumed = bm.migrate_backlog_if_legacy(cfg, FROM, TO)
    assert resumed.state == "migrated" and resumed.generator_check_exit == 0, resumed.detail
    assert sup.classify_shape(mig.read_text(backlog / INDEX))[0] == "migrated"
    budget_sweep(cfg)
    after = _snapshot(cfg.project_root)
    assert bm.migrate_backlog_if_legacy(cfg, FROM, TO).state == "generated"
    assert _snapshot(cfg.project_root) == after


def test_bullet_naming_an_unknown_item_is_relocated_to_the_changelog(tmp_path):
    # Assertion 8: the control. A bullet whose owner has no item file lands in the relocated entry.
    bullet = "- 009 relates to 001 (shared parser)"
    cfg, backlog = _project(tmp_path, legacy_index(bullet=bullet))
    report = bm.migrate_backlog_if_legacy(cfg, FROM, TO)
    assert report.state == "migrated", report.detail
    log = (backlog / "00-Changelog-Backlog.md").read_text(encoding="utf-8")
    assert "Relocated index text (migrated " in log and f"(unknown-owner bullet): {bullet}" in log
    assert report.counts["changelog_unaccounted"] == 0


def _long_entry(k: int, sentences: int) -> str:
    return f"2023-{k:02d}-01 — " + " ".join(f"change {k}.{j} was recorded in the backlog history."
                                           for j in range(sentences))


def test_oversize_changelog_is_split_into_budgeted_parts(tmp_path):
    # Assertion 10: a footer whose entries total above READ_TOKEN_WARN.
    entries = [_long_entry(k, 420) for k in range(1, 5)]
    footer_bytes = len(footer(entries).encode("utf-8"))
    assert budget._measure(footer(entries))[1] > READ_TOKEN_WARN, footer_bytes
    cfg, backlog = _project(tmp_path, legacy_index(entries=entries))
    original_index = (backlog / INDEX).read_bytes()

    report = bm.migrate_backlog_if_legacy(cfg, FROM, TO)
    assert report.state == "migrated", report.detail
    files = _changelog_files(backlog)
    assert len(files) >= 2
    texts = [mig.read_text(p) for p in files]
    ledger = json.loads(mig.read_text(report.ledger_path))
    assert ledger["changelog"]["unaccounted"] == 0
    log = sup.joined_entries(texts)
    assert all(s.decode("utf-8") in log for s in sup.extract_changelog(original_index)["segments"])
    budget_sweep(cfg)  # assertion 9 stays green

    after = _snapshot(cfg.project_root)
    again = bm.migrate_backlog_if_legacy(cfg, FROM, TO)
    assert again.state == "generated", again.detail
    assert _snapshot(cfg.project_root) == after


def test_one_footer_entry_over_budget_alone_is_refused_by_name(tmp_path):
    # Assertion 10, second half: a footer entry is one line, so an entry over the budget on its
    # own has no paragraph boundary. The migration refuses it by name and never splits it mid-line.
    entries = [_long_entry(k, 420) for k in range(1, 5)]
    entries[1] = _long_entry(2, 1400)
    assert budget._measure(entries[1])[1] > READ_TOKEN_WARN
    cfg, _backlog = _project(tmp_path, legacy_index(entries=entries))
    before = _snapshot(cfg.project_root)

    report = bm.migrate_backlog_if_legacy(cfg, FROM, TO)
    assert report.state == "refused", report.detail
    assert f"changelog entry 2, which begins {entries[1][:60]!r}, is one paragraph of ~" in report.detail
    assert "no paragraph boundary" in report.detail and "never splits an entry mid-line" in report.detail
    assert report.fix.startswith("shorten entry 2 by hand, or split it into smaller entries, then re-run"), report.fix
    assert _snapshot(cfg.project_root) == before
    assert not _backups(cfg).exists()


@pytest.mark.parametrize("second_pair", [("1.0.5.2", "1.0.5.3"), (FROM, TO)], ids=["next-pair", "same-pair"])
def test_changelog_grown_past_budget_is_resplit_on_upgrade(tmp_path, second_pair):
    # Assertion 11: re-split on upgrade.
    cfg, backlog = _project(tmp_path)
    assert bm.migrate_backlog_if_legacy(cfg, FROM, TO).state == "migrated"
    budget_sweep(cfg)
    part1 = backlog / CHANGELOG
    migrated_part1 = part1.read_bytes()
    grown = mig.read_text(part1)
    k = 4
    while budget._measure(grown.replace("\r\n", "\n"))[1] <= READ_TOKEN_WARN:
        paragraphs = "\n\n".join(f"Paragraph {k}.{j}: " + "the backlog grew after its migration. " * 9
                                 for j in range(40))
        grown += f"## Entry {k}\n\n{paragraphs}\n\n"
        k += 1
    # One entry larger than the budget alone, so the re-split must continue it across parts.
    big = "\n\n".join(f"Paragraph {k}.{j}: " + "one entry outgrew a whole part. " * 9 for j in range(260))
    grown += f"## Entry {k}\n\n{big}\n\n"
    assert budget._measure(f"## Entry {k}\n\n{big}\n\n")[1] > READ_TOKEN_WARN
    _write(part1, grown)
    pre_resplit = part1.read_bytes()

    report = bm.migrate_backlog_if_legacy(cfg, *second_pair)
    assert report.state == "changelog_split", report.detail
    pair_dir = _backups(cfg, f"{second_pair[0]}-to-{second_pair[1]}") / "backlog"
    if second_pair == (FROM, TO):
        # Same pair: the first pre-image is kept, and the diverged one lands in a `.1.bak` sibling.
        assert (pair_dir / CHANGELOG).read_bytes() == HEADER_ONLY.encode("utf-8")
        assert (pair_dir / f"{CHANGELOG}.1.bak").read_bytes() == pre_resplit
    else:
        assert (pair_dir / CHANGELOG).read_bytes() == pre_resplit
    assert migrated_part1 != pre_resplit
    files = _changelog_files(backlog)
    assert len(files) == report.counts["changelog_parts"] >= 2
    texts = [mig.read_text(p) for p in files]
    assert any(f"## Entry {k} (continued)" in t for t in texts)
    assert sup.parse_changelog([t for t in texts]) == sup.parse_changelog([grown])
    budget_sweep(cfg)

    after = _snapshot(cfg.project_root)
    third = bm.migrate_backlog_if_legacy(cfg, *second_pair)
    assert third.state == "generated", third.detail
    assert _snapshot(cfg.project_root) == after
