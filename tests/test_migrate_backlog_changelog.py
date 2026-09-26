"""Tests for the changelog budget (design D15): numbered parts, each under
the read-gate warn, `split_changelog`/`parse_changelog` as pure functions,
the multi-part migration path, `--split-changelog`, and the `--report`
budget keys. Fixtures are written as bytes under tmp_path, never under
plugins/planwise/. Large entries are generated in code, never spelled out."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import backlog_index_schema as schema  # noqa: E402
import migrate_backlog_index as mig  # noqa: E402
import migrate_backlog_support as sup  # noqa: E402

NO_GIT = "--allow-untracked-tree"
HEADER = "| ID | Feature | Priority | Status | Created | Blocks | Files |\n|---|---|---|---|---|---|---|\n"
FOOTER = "*Last Updated: 2024-01-01 — did something. Prior entry: 2023-12-01 — did something else.*\n"
HEADER_ONLY = "[← 00-Index-Backlog.md](00-Index-Backlog.md)\n"
NAMES = {"001": "ITM-001-SMP-First.md", "002": "ITM-002-SMP-Second.md"}
TITLES = {"001": "First sample item", "002": "Second sample item"}


def fm(item_id):
    keys = {"id": item_id, "title": f'"{TITLES[item_id]}"', "priority": "High", "status": "NOT_STARTED",
            "abbrev": "SMP", "created": "2024-01-01", "blocks": "[]"}
    return "\n".join(["---"] + [f"{k}: {v}" for k, v in keys.items()] + ["---", ""]) + "\n"


def item(item_id):
    return fm(item_id) + f"# {TITLES[item_id]}\n\nBody text.\n"


def row(item_id):
    return f"| {item_id} | {TITLES[item_id]} | High | NOT_STARTED | 2024-01-01 | | [{item_id}]({NAMES[item_id]}) |\n"


def index(*rows, footer=FOOTER):
    return f"# Backlog Index\n\n## Backlog Items\n\n{HEADER}{''.join(rows)}\n{footer}"


def project(tmp_path, index_text, items, changelog=None):
    planwise = tmp_path / "proj" / "planwise"
    backlog = planwise / "Backlog"
    (backlog / "Archive").mkdir(parents=True)
    for item_id, text in items.items():
        (backlog / NAMES[item_id]).write_bytes(text.encode("utf-8"))
    (planwise / "config.yaml").write_bytes(b'project:\n  name: "test-project"\n  backlog_dir: "Backlog"\n'
                                           b'  index_files:\n    backlog: "00-Index-Backlog.md"\n')
    index_path = backlog / "00-Index-Backlog.md"
    index_path.write_bytes(index_text.encode("utf-8"))
    if changelog is not None:
        (backlog / "00-Changelog-Backlog.md").write_bytes(changelog.encode("utf-8"))
    return planwise / "config.yaml", index_path


def snapshot(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def run(monkeypatch, capsys, config_path, *args):
    monkeypatch.setattr(sys, "argv", ["migrate_backlog_index.py", "--config", str(config_path), NO_GIT, *args])
    code = mig.main()
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def ledger(index_path):
    return json.loads(mig.artifact_paths(index_path)[1].read_bytes().decode("utf-8"))


def big_footer(n, size_each):
    """A single-line legacy footer with `n` entries, each `size_each` UTF-8
    bytes of generated filler (no embedded blank lines -- exactly what a
    real hand-authored footer line can hold)."""
    filler = "padding text for a large changelog entry "
    body = (filler * (size_each // len(filler) + 1))[:size_each]
    entries = [f"2024-0{i + 1}-01 — {body} #{i}" for i in range(n)]
    return "*Last Updated: " + " Prior entry: ".join(entries) + "*\n"


def multi_part_fixture():
    """(naming, entries, budget) sized so 3 entries split into >= 2 parts,
    each comfortably under budget -- the header/Parts-line overhead stays a
    small fraction of the budget, unlike a toy-scale budget would leave it."""
    naming = schema._index_naming(Path("00-Index-Backlog.md"))
    entries = [(f"Entry {i} " + "padding " * 50).encode() for i in range(1, 4)]
    one_entry_tokens = sup.changelog_tokens(f"## Entry 1\n\n{entries[0].decode()}\n\n")
    return naming, entries, one_entry_tokens + one_entry_tokens // 2


def promote_to_migrated(config_path):
    """Run the generator over an already footer-migrated legacy index, so
    its shape becomes `migrated` (Sequence step 4 of the module docstring)."""
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "generate_backlog_index.py"), "--config", str(config_path),
         "--write", "--replace-legacy"], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    return result


# --- pure-function tests: split_changelog / parse_changelog -----------------

def test_n_equals_1_is_byte_identical_to_changelog_text():
    naming = schema._index_naming(Path("00-Index-Backlog.md"))
    segments = [b"first entry text here.", b"second entry text here."]
    result = sup.split_changelog(segments, naming, "00-Index-Backlog.md", "\n")
    assert len(result) == 1
    name, text = result[0]
    assert name == "00-Changelog-Backlog.md"
    assert text == sup.changelog_text(segments, "00-Index-Backlog.md", "\n")


def test_over_budget_footer_gives_multiple_parts_each_under_budget():
    naming, entries, budget = multi_part_fixture()
    result = sup.split_changelog(entries, naming, "00-Index-Backlog.md", "\n", budget=budget)
    assert len(result) >= 2
    for _name, text in result:
        assert sup.changelog_tokens(text) < budget


def test_oversized_entry_gets_a_continued_section():
    naming = schema._index_naming(Path("00-Index-Backlog.md"))
    para = "Padding text for one paragraph of the oversized entry. " * 4
    body = "\n\n".join(f"{para}{i}" for i in range(5))
    single_para_tokens = sup.changelog_tokens(f"## Entry 1\n\n{para}0\n\n")
    whole_tokens = sup.changelog_tokens(f"## Entry 1\n\n{body}\n\n")
    budget = single_para_tokens + 20
    assert whole_tokens >= budget, "test setup must actually force a split"
    segments = [body.encode("utf-8")]
    result = sup.split_changelog(segments, naming, "00-Index-Backlog.md", "\n", budget=budget)
    joined = "".join(t for _n, t in result)
    assert "## Entry 1 (continued)" in joined
    assert sup.parse_changelog([t for _n, t in result]) == segments


def test_single_oversized_paragraph_is_refused():
    naming = schema._index_naming(Path("00-Index-Backlog.md"))
    body = "One giant paragraph with no blank line inside it at all, " * 20
    segments = [body.encode("utf-8")]
    tight_budget = sup.changelog_tokens(f"## Entry 1\n\n{body}\n\n") - 5
    with pytest.raises(sup.Refusal, match=r"entry 1 has a paragraph"):
        sup.split_changelog(segments, naming, "00-Index-Backlog.md", "\n", budget=tight_budget)


def test_split_is_deterministic():
    naming, entries, budget = multi_part_fixture()
    first = sup.split_changelog(entries, naming, "00-Index-Backlog.md", "\n", budget=budget)
    second = sup.split_changelog(entries, naming, "00-Index-Backlog.md", "\n", budget=budget)
    assert first == second


def test_parse_split_round_trip():
    naming, entries, budget = multi_part_fixture()
    result = sup.split_changelog(entries, naming, "00-Index-Backlog.md", "\n", budget=budget)
    assert sup.parse_changelog([t for _n, t in result]) == entries


def test_part_names_start_with_00_and_are_not_generated_index_files():
    naming, entries, budget = multi_part_fixture()
    result = sup.split_changelog(entries, naming, "00-Index-Backlog.md", "\n", budget=budget)
    assert len(result) >= 2
    for name, _text in result:
        assert name.startswith("00-")
        assert schema.is_generated_index_file(name, naming) is False


def test_foreign_text_in_a_part_is_refused():
    with pytest.raises(sup.Refusal):
        sup.parse_changelog(["not a backlink line at all\n\n## Entry 1\n\nbody\n\n"])
    with pytest.raises(sup.Refusal):
        sup.parse_changelog(["[← 00-Index-Backlog.md](00-Index-Backlog.md)\n\n## Entry 1\n\nbody\n\n"
                              "## Unexpected Heading\n\nmore\n\n"])


# --- CLI-level tests: real migration, --split-changelog, --report ----------

def test_cli_oversize_fixture_writes_parts_and_reruns_clean(tmp_path, monkeypatch, capsys):
    footer = big_footer(3, 22000)
    items = {"001": item("001"), "002": item("002")}
    text = index(row("001"), row("002"), footer=footer)
    config_path, index_path = project(tmp_path, text, items)
    code, out, err = run(monkeypatch, capsys, config_path, "--write")
    assert code == 0, err + out
    naming = schema._index_naming(index_path)
    part1 = index_path.with_name(schema._changelog_filename(naming))
    part2 = index_path.with_name(sup.changelog_part_filename(naming, 2))
    assert part1.exists() and part2.exists()
    for part in (part1, part2):
        assert sup.changelog_tokens(part.read_bytes().decode("utf-8")) < 22000
    log = ledger(index_path)
    assert log["changelog"]["unaccounted"] == 0
    assert len(log["changelog"]["parts"]) == 2
    after = snapshot(tmp_path)
    code, out, err = run(monkeypatch, capsys, config_path, "--write")
    assert code == 0 and "CLEAN" in out, err + out
    assert snapshot(tmp_path) == after


def test_stale_part_file_beyond_planned_n_is_refused(tmp_path, monkeypatch, capsys):
    items = {"001": item("001")}
    config_path, index_path = project(tmp_path, index(row("001")), items)
    naming = schema._index_naming(index_path)
    stale = index_path.with_name(sup.changelog_part_filename(naming, 9))
    stale.write_bytes(b"stray leftover part\n")
    before = snapshot(tmp_path)
    code, out, err = run(monkeypatch, capsys, config_path, "--force", "--write")
    assert code == 2, err + out
    assert stale.name in err
    assert snapshot(tmp_path) == before


def test_split_changelog_within_budget_is_a_noop(tmp_path, monkeypatch, capsys):
    items = {"001": item("001")}
    config_path, index_path = project(tmp_path, index(row("001")), items)
    code, out, err = run(monkeypatch, capsys, config_path, "--write")
    assert code == 0, err + out
    promote_to_migrated(config_path)
    before = snapshot(tmp_path)
    code, out, err = run(monkeypatch, capsys, config_path, "--split-changelog")
    assert code == 0 and "within budget" in out, err + out
    assert snapshot(tmp_path) == before


def test_split_changelog_over_budget_resplits_and_then_is_stable(tmp_path, monkeypatch, capsys):
    items = {"001": item("001")}
    config_path, index_path = project(tmp_path, index(row("001")), items)
    code, out, err = run(monkeypatch, capsys, config_path, "--write")
    assert code == 0, err + out
    promote_to_migrated(config_path)
    naming = schema._index_naming(index_path)
    part1 = index_path.with_name(schema._changelog_filename(naming))
    big_segments = [f"padding {'x' * 21000} entry {i}".encode() for i in range(3)]
    grown = sup.changelog_text(big_segments, index_path.name, "\n")
    part1.write_bytes(grown.encode("utf-8"))
    code, out, err = run(monkeypatch, capsys, config_path, "--split-changelog", "--write")
    assert code == 0, err + out
    pattern = sup.changelog_part_pattern(naming)
    files = [p for p in index_path.parent.iterdir() if p.name == part1.name or pattern.match(p.name)]
    assert len(files) >= 2
    for p in files:
        assert sup.changelog_tokens(p.read_bytes().decode("utf-8")) < 22000
    before = snapshot(tmp_path)
    code, out, err = run(monkeypatch, capsys, config_path, "--split-changelog")
    assert code == 0 and "within budget" in out, err + out
    assert snapshot(tmp_path) == before


def test_split_changelog_on_legacy_index_exits_2(tmp_path, monkeypatch, capsys):
    items = {"001": item("001")}
    config_path, _index_path = project(tmp_path, index(row("001")), items)
    code, out, err = run(monkeypatch, capsys, config_path, "--split-changelog")
    assert code == 2, err + out
    assert "migration first" in err


def test_report_carries_changelog_budget_keys(tmp_path, monkeypatch, capsys):
    items = {"001": item("001")}
    config_path, _index_path = project(tmp_path, index(row("001")), items, changelog=HEADER_ONLY)
    code, out, err = run(monkeypatch, capsys, config_path, "--report")
    assert code == 0, err + out
    report = json.loads(out)
    assert "changelog_files" in report and "changelog_over_budget" in report
    assert report["changelog_over_budget"] is False
    assert report["changelog_files"][0]["level"] == "OK"


@pytest.mark.parametrize("nl", ["\n", "\r\n"])
def test_lf_and_crlf_preserved_per_part(tmp_path, monkeypatch, capsys, nl):
    text, item_text = index(row("001")), item("001")
    if nl == "\r\n":
        text, item_text = text.replace("\n", "\r\n"), item_text.replace("\n", "\r\n")
    config_path, index_path = project(tmp_path, text, {"001": item_text})
    code, out, err = run(monkeypatch, capsys, config_path, "--write")
    assert code == 0, err + out
    naming = schema._index_naming(index_path)
    part1 = index_path.with_name(schema._changelog_filename(naming))
    raw = part1.read_bytes()
    if nl == "\r\n":
        assert raw.count(b"\r\n") > 0 and raw.count(b"\r\n") == raw.count(b"\n")
    else:
        assert b"\r\n" not in raw


def test_generator_coexists_with_changelog_parts(tmp_path, monkeypatch, capsys):
    items = {"001": item("001"), "002": item("002")}
    config_path, index_path = project(tmp_path, index(row("001"), row("002")), items)
    code, out, err = run(monkeypatch, capsys, config_path, "--write")
    assert code == 0, err + out
    promote_to_migrated(config_path)
    naming = schema._index_naming(index_path)
    part1 = index_path.with_name(schema._changelog_filename(naming))
    part2 = index_path.with_name(sup.changelog_part_filename(naming, 2))
    part3 = index_path.with_name(sup.changelog_part_filename(naming, 3))
    part2.write_bytes(f"[← {part1.name}]({part1.name})\n\n## Entry 1\n\nExtra part two.\n\n".encode("utf-8"))
    part3.write_bytes(f"[← {part1.name}]({part1.name})\n\n## Entry 1\n\nExtra part three.\n\n".encode("utf-8"))
    for path in (part1, part2, part3):
        assert not schema.is_generated_index_file(path.name, naming)
    before = {p.name: p.read_bytes() for p in (part1, part2, part3)}
    promote_to_migrated(config_path)
    check = subprocess.run(
        [sys.executable, str(SCRIPTS / "generate_backlog_index.py"), "--config", str(config_path), "--check"],
        capture_output=True, text=True, check=False)
    assert check.returncode == 0, check.stdout + check.stderr
    after = {p.name: p.read_bytes() for p in (part1, part2, part3)}
    assert after == before
