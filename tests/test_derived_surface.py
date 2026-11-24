"""Tests for the derived session surface: rendered by scaffold_plan, priced by token_saver_writeback.

Every fixture is the real renderer's output, written to a project under tmp_path and priced by the
real write-back. No surface row is typed by hand.
"""

import re
import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import scaffold_plan as sp
import token_saver_writeback as tsw

TEMPLATES = sp.DEFAULT_TEMPLATES
SPRINT = "Sprint-01-LedgerCore"
READ_PATH = f"{SPRINT}/Session-01-ReadPath"
ORCH = f"{READ_PATH}/QZX-S01-01-Orchestration.md"
RECOVERY = f"{READ_PATH}/QZX-S01-01-Recovery.md"
TASK_1 = f"{READ_PATH}/QZX-S01-01-01-Haiku-ParseRows.md"
TASK_2 = f"{READ_PATH}/QZX-S01-01-02-Opus-IndexRows.md"
OTHER_ORCH = f"{SPRINT}/Session-02-WritePath/QZX-S01-02-Orchestration.md"
OTHER_TASK = f"{SPRINT}/Session-02-WritePath/QZX-S01-02-01-Sonnet-WriteRows.md"
LEDGER = "src/orchard/ledger.py"
PARSE = "src/orchard/parse.py"
CREATE = "CREATE (plan-time estimate)"


def _row(path, tokens_k, **extra):
    return {"priority": 1, "path": path, "kib": tokens_k * 2, "tokens_k": tokens_k, "purpose": "a file", **extra}


def _task(number, name, agent, outputs, rows):
    return {"number": number, "name": name, "title": f"Step {number}", "agent": agent, "estimate_k": 20,
            "depends_on": [], "outputs": outputs, "required_context": rows}


def make_spec():
    span = _row(LEDGER, 1.5, kind="span", span="lines 1-10")
    command = {"kind": "command", "priority": 3, "command": "Grep 'ledger' over src/calls.py", "lines": 12,
               "bytes": "~900", "kib": 0.9, "tokens_k": 0.4, "purpose": "call sites"}
    first = _task(1, "ParseRows", "Haiku", [PARSE, "Outputs/QZX-parse.md"],
                  [span, command, _row(PARSE, 0.7), _row("Outputs/QZX-parse.md", 0.3)])
    second = _task(2, "IndexRows", "Opus", [LEDGER],
                   [_row(".\\src\\orchard\\ledger.py", 3.0), _row("docs/guide.md", 0.8),
                    _row(f"plans/QZX/{READ_PATH}/Outputs/QZX-parse.md", 0.6),
                    _row("QZX-S01-01-Recovery.md", 0.2)])
    other = _task(1, "WriteRows", "Sonnet", ["src/orchard/write.py"],
                  [_row("docs/other.md", 0.5), _row("docs\\later.md", 0.5)])  # later.md is absent
    return {
        "plan_name": "OrchardLedger", "abbrev": "QZX", "created": "2030-01-15", "ordering": "Sprint one only",
        "sprints": [{"number": 1, "name": "LedgerCore", "purpose": "Build the core", "sessions": [
            {"number": 1, "name": "ReadPath", "objective": "Read", "mode": "DELEGATED",
             "prerequisite": "None", "tasks": [first, second]},
            {"number": 2, "name": "WritePath", "objective": "Write", "mode": "DIRECT",
             "prerequisite": "The read path", "tasks": [other]}]}],
    }


class Tree:
    """A rendered plan in a project folder, with the subtotal fills answered."""

    def __init__(self, base, eol="\n"):
        self.root = base / "project"
        self.plan = self.root / "plans/QZX"
        for rel, text in (("src/orchard/ledger.py", "ledger = {}\n" * 900), ("docs/guide.md", "A rule.\n" * 300),
                          ("docs/other.md", "Other.\n" * 200)):
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(text.encode("utf-8"))
        self.files = sp.render_all(make_spec(), TEMPLATES, project_root=self.root)[0]
        sp.write_tree({rel: text.replace("<!-- FILL: {O} -->", "2").replace("<!-- FILL: {W} -->", "1")
                       .replace("\n", eol) for rel, text in self.files.items()}, self.plan)

    def text(self, rel):
        return (self.plan / rel).read_bytes().decode("utf-8")

    def set(self, rel, text):
        (self.plan / rel).write_bytes(text.encode("utf-8"))

    def write_back(self, *rels):
        report = tsw.write_estimates([self.plan / r for r in rels], self.plan, self.root)
        assert report["errors"] == []
        return report

    def snapshot(self):
        return {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}


@pytest.fixture
def tree(tmp_path):
    return Tree(tmp_path)


def _block(text):
    parts = text.replace("\r\n", "\n").split("\n## Session Surface", 1)
    assert len(parts) == 2
    return parts[1].split("\n---\n", 1)[0]


def _rows(text):
    """{path: [role, KiB, ~Tokens, cited by]} of the block, every path once and every cell filled."""
    table = [ln for ln in _block(text).split("\n") if ln.startswith("|")]
    assert table[0] == "| Path | Role | KiB | ~Tokens | Cited By |"
    cells = [[c.strip() for c in sp.split_row_cells(ln)] for ln in table[2:]]
    assert all(len(c) == 5 and all(c) for c in cells), cells
    out = {c[0].strip("`"): c[1:] for c in cells}
    assert len(out) == len(cells), cells  # one row per path
    return out


def _assert_total(text):
    rows = _rows(text)
    line = next(ln for ln in _block(text).split("\n") if ln.startswith("**Session surface:**"))
    total = sum(Decimal(r[2].strip("~K")) for r in rows.values())
    assert line == f"**Session surface:** ~{total}K tokens over {len(rows)} files (information only)"


def _task_figure(text, cell):
    """The (KiB, ~Tokens) cells of one task row."""
    row = next(ln for ln in text.replace("\r\n", "\n").split("\n") if ln.startswith("|") and cell in ln)
    cells = [c.strip() for c in sp.split_row_cells(row)]
    return cells[2], cells[3]


def test_a_path_two_tasks_cite_appears_once_with_the_higher_figure(tree):
    role, kib, tokens, cited = _rows(tree.files[ORCH])[LEDGER]
    assert (role, kib, tokens, cited) == ("EDIT", "6.0", "~3.0K", "01, 02")  # the seed
    tree.write_back(TASK_1, TASK_2)
    span = _task_figure(tree.text(TASK_1), "ledger.py` lines 1-10")
    whole = _task_figure(tree.text(TASK_2), "ledger.py`")
    assert Decimal(span[1].strip("~K")) < Decimal(whole[1].strip("~K"))
    assert whole[1] != "~3.0K"  # the control: the write-back moved the figure
    assert _rows(tree.text(ORCH))[LEDGER] == ["EDIT", *whole, "01, 02"]


def test_the_plan_files_come_first_and_sessions_never_mix(tree):
    names = [Path(rel).name for rel in (ORCH, RECOVERY, TASK_1, TASK_2)]
    other = [Path(OTHER_ORCH).name, "QZX-S01-02-Recovery.md", Path(OTHER_TASK).name,
             "docs/later.md", "docs/other.md"]
    outputs = f"{READ_PATH}/Outputs/QZX-parse.md"
    assert list(_rows(tree.files[ORCH])) == [*names, outputs, "docs/guide.md", LEDGER, PARSE]
    assert list(_rows(tree.files[OTHER_ORCH])) == other
    tree.write_back(TASK_1, TASK_2, OTHER_TASK)
    rows = _rows(tree.text(ORCH))
    assert list(rows) == [*names, outputs, "docs/guide.md", LEDGER, PARSE]
    assert list(_rows(tree.text(OTHER_ORCH))) == other
    assert rows[names[0]][3] == "orchestrator"
    assert rows[names[1]][3] == "orchestrator, 02"
    for rel in (ORCH, RECOVERY, TASK_1):
        assert rows[Path(rel).name][1] == sp._fmt_kib((tree.plan / rel).stat().st_size), rel
    # The higher of the two task models prices a plan file. No task cites the Orchestration.
    size = (tree.plan / ORCH).stat().st_size
    doc = sp.content_class_for(Path("x.md"))[1]
    prices = [sp._fmt_k(sp.estimate_tokens(size, model, doc)) for model in ("haiku", "opus")]
    assert Decimal(prices[0].strip("~K")) < Decimal(prices[1].strip("~K"))  # the control: the models differ
    assert rows[names[0]][2] == prices[1]


def test_the_total_is_the_sum_of_the_cells_and_no_session_total_reads_it(tree):
    for rel in (ORCH, OTHER_ORCH):
        _assert_total(tree.files[rel])
    tree.write_back(TASK_1, TASK_2, OTHER_TASK)
    for rel in (ORCH, OTHER_ORCH):
        _assert_total(tree.text(rel))
    headers = [re.search(r"^\*\*Estimated Tokens:\*\* ~([\d.]+)K", tree.text(rel), re.MULTILINE).group(1)
               for rel in (TASK_1, TASK_2)]
    total = re.search(r"^\*\*Total Estimated:\*\* ~([\d.]+)K", tree.text(ORCH), re.MULTILINE).group(1)
    assert Decimal(total) == sum(map(Decimal, headers))


@pytest.mark.parametrize("eol", ["\n", "\r\n"], ids=["lf", "crlf"])
def test_a_second_write_back_changes_no_byte(tmp_path, eol):
    tree = Tree(tmp_path, eol)
    # Without its body rows the file is smaller, so one pass would price the own row too low.
    text = tree.text(ORCH)
    body = [ln for ln in text.split("\n") if re.match(r"\| `.*(orchestrator|0\d) \|\r?$", ln)]
    assert len(body) == len(_rows(text))
    short = "\n".join(ln for ln in text.split("\n") if ln not in body)
    assert sp._fmt_kib(len(short.encode("utf-8"))) != sp._fmt_kib(len(text.encode("utf-8")))
    tree.set(ORCH, short)
    assert tree.write_back(TASK_1, TASK_2)["written"]
    before = tree.snapshot()
    report = tree.write_back(TASK_1, TASK_2)
    assert (report["written"], report["changes"]) == ([], [])
    assert tree.snapshot() == before
    data = (tree.plan / ORCH).read_bytes()
    assert data.count(b"\r\n") == (data.count(b"\n") if eol == "\r\n" else 0)
    assert _rows(tree.text(ORCH))[Path(ORCH).name][1] == sp._fmt_kib(len(data))


def test_naming_one_task_builds_the_block_from_every_task_file(tree):
    tree.write_back(TASK_2)
    rows = _rows(tree.text(ORCH))
    assert rows[PARSE][3] == "01"
    assert rows[LEDGER][3] == "01, 02"
    _assert_total(tree.text(ORCH))
    assert tree.text(OTHER_ORCH) == tree.files[OTHER_ORCH]  # the unnamed session keeps its render


def test_roles_flags_and_outputs_paths(tree):
    for text in (tree.files[ORCH], (tree.write_back(TASK_1, TASK_2), tree.text(ORCH))[1]):
        rows = _rows(text)
        assert rows[PARSE] == [CREATE, "1.4", "~0.7K", "01"]  # absent, so both cells stay the seed
        # Two spellings of one absent output: the higher figure and the higher role.
        assert rows[f"{READ_PATH}/Outputs/QZX-parse.md"] == [CREATE, "1.2", "~0.6K", "01, 02"]
        assert rows["docs/guide.md"][0] == "READ"
        assert "Grep" not in _block(text)


def test_an_old_shape_task_table_feeds_the_block_as_read(tree):
    lines = tree.text(TASK_2).split("\n")
    head = next(i for i, ln in enumerate(lines) if ln.startswith("| Priority | File | KiB |"))
    for i in range(head, head + 7):
        cells = sp.split_row_cells(lines[i])
        assert len(cells) == 6
        lines[i] = "| " + " | ".join(c.strip() for c in cells[:4] + cells[5:]) + " |"
    tree.set(TASK_2, "\n".join(lines))
    tree.write_back(TASK_2)
    role, _kib, tokens, cited = _rows(tree.text(ORCH))[LEDGER]
    assert (role, cited) == ("READ", "01, 02")
    assert tokens == _task_figure(tree.text(TASK_2), "ledger.py`")[1]


def _without_block(text):
    head, rest = text.split("## Session Surface", 1)
    return head + rest.split("\n---\n\n", 1)[1]


def test_an_orchestration_with_no_block_is_untouched_by_the_block_pass(tmp_path, monkeypatch):
    results = []
    for name in ("with_pass", "no_pass"):
        (tmp_path / name).mkdir()
        tree = Tree(tmp_path / name)
        tree.set(ORCH, _without_block(tree.text(ORCH)))
        if name == "no_pass":
            monkeypatch.setattr(tsw, "_write_session_surface", lambda *_args: None)
        report = tree.write_back(TASK_1, TASK_2)
        assert report["unreadable"] == []
        assert not [r for r in report["left"] if "Orchestration" in r["file"]]
        results.append(tree.text(ORCH))
    assert results[0] == results[1]
    assert "Session Surface" not in results[0] and "**Session surface:**" not in results[0]


def test_a_failed_block_pass_keeps_every_other_write(tree, monkeypatch):
    def boom(*_args):
        raise RuntimeError("planted")

    block = _block(tree.text(ORCH))
    monkeypatch.setattr(tsw, "surface_entries", boom)
    report = tree.write_back(TASK_1, TASK_2)
    assert [(u["what"], u["reason"]) for u in report["unreadable"]] == [
        ("Session Surface", "RuntimeError: planted")]
    written = {Path(p).name for p in report["written"]}
    assert written == {Path(TASK_1).name, Path(TASK_2).name, Path(ORCH).name, "QZX-S01-Sprint-Plan.md"}
    assert _block(tree.text(ORCH)) == block


def test_the_block_is_priced_when_the_task_list_cannot_be(tree):
    tree.set(ORCH, tree.text(ORCH).replace("| 2 | IndexRows: ", "| 9 | IndexRows: "))
    report = tree.write_back(TASK_1, TASK_2)
    assert [u["what"] for u in report["unreadable"]] == ["task row QZX-S01-01-02"]
    assert _rows(tree.text(ORCH))[LEDGER][1:3] == list(_task_figure(tree.text(TASK_2), "ledger.py`"))


def test_a_plan_file_that_cannot_be_priced_keeps_its_figure(tree):
    tree.write_back(OTHER_TASK)
    name = "QZX-S01-02-Recovery.md"  # no task cites it
    kept = _rows(tree.text(OTHER_ORCH))[name]
    assert kept[0] == "READ" and kept[1] != "0.0"
    (tree.plan / SPRINT / "Session-02-WritePath" / name).unlink()
    report = tree.write_back(OTHER_TASK)
    assert report["unreadable"] == []
    assert _rows(tree.text(OTHER_ORCH))[name] == kept


def test_a_path_with_no_figure_prints_zero_and_the_flag(tree):
    text = tree.text(TASK_1)
    row = next(ln for ln in text.split("\n") if ln.startswith("|") and f"`{PARSE}`" in ln)
    entries = tsw.surface_entries(
        [(tree.plan / TASK_1, text.replace(row, row.replace("~0.7K", "n/a")))], [], tree.plan, tree.root)
    got = next(tsw.surface_row(e) for e in entries if e["path"] == PARSE)
    assert got == f"| `{PARSE}` | {CREATE} | 0.0 | ~0.0K | 01 |"
    # A task file that no row cites has no figure either, and no cell stays blank.
    bare = tsw.surface_entries([(Path("s/p/T-01-Opus-X.md"), "no table")], [], tree.plan, tree.root)
    assert tsw.surface_row(bare[0]) == "| `T-01-Opus-X.md` | READ (plan-time estimate) | 0.0 | ~0.0K | none |"


def _add_rows(tree, *cells):
    """Add one row per File cell to the second task, each a copy of its rendered guide row."""
    text = tree.text(TASK_2)
    row = next(ln for ln in text.split("\n") if ln.startswith("|") and "`docs/guide.md`" in ln)
    tree.set(TASK_2, text.replace(row, "\n".join([row, *(row.replace("`docs/guide.md`", c) for c in cells)])))


def _assert_settled(tree):
    before = tree.snapshot()
    report = tree.write_back(TASK_1, TASK_2)
    assert (report["written"], report["changes"]) == ([], [])
    assert tree.snapshot() == before


def test_a_qualified_cell_is_the_file_it_names(tree):
    (tree.root / "C").write_bytes(b"one file\n")
    for name in ("docs/plan", "docs/plan (old)"):
        (tree.root / name).write_bytes(b"a plan\n")
    recovery = Path(RECOVERY).name
    _add_rows(tree, "`docs/guide.md` (first half)", "`docs/guide.md`:1-10", "`docs/guide.md:7` (a rule)",
              "`docs/plan`", "`docs/plan (old)`", "`docs/absent.md:1-10`", "`C:5`", f"`{recovery}` (state)")
    before = list(_rows(tree.files[ORCH]))
    tree.write_back(TASK_1, TASK_2)
    rows = _rows(tree.text(ORCH))
    # A raw path that resolves, a path that resolves neither way and a drive colon keep their own rows.
    assert set(rows) == {*before, "docs/plan", "docs/plan (old)", "docs/absent.md:1-10", "C:5"}
    assert rows[recovery][3] == "orchestrator, 02"
    _assert_total(tree.text(ORCH))
    _assert_settled(tree)


def test_a_trailing_slash_names_the_same_directory(tree):
    _add_rows(tree, "`src/orchard`", "`src/orchard/`", "`.\\src\\orchard\\`")
    before = list(_rows(tree.files[ORCH]))
    tree.write_back(TASK_1, TASK_2)
    assert set(_rows(tree.text(ORCH))) == {*before, "src/orchard"}
    _assert_settled(tree)


def _surface_changes(report):
    return [(c["old"], c["new"]) for c in report["changes"] if c["what"] == "Session Surface"]


def test_a_reordered_row_leaves_a_change_record(tree):
    tree.write_back(TASK_1, TASK_2)
    settled = tree.text(ORCH)
    first, second = (next(ln for ln in settled.split("\n") if ln.startswith(f"| `{p}` |"))
                     for p in ("docs/guide.md", LEDGER))
    tree.set(ORCH, settled.replace(f"{first}\n{second}", f"{second}\n{first}"))
    assert tree.text(ORCH) != settled
    report = tree.write_back(TASK_1, TASK_2)
    assert tree.text(ORCH) == settled
    assert [Path(p).name for p in report["written"]] == [Path(ORCH).name]
    assert len(_surface_changes(report)) == 1  # the order, and no cell
    _assert_settled(tree)


def test_a_removed_duplicate_row_leaves_a_change_record(tree):
    tree.write_back(TASK_1, TASK_2)
    settled = tree.text(ORCH)
    row = next(ln for ln in settled.split("\n") if ln.startswith("| `docs/guide.md` |"))
    tree.set(ORCH, settled.replace(row, f"{row}\n{row}"))
    report = tree.write_back(TASK_1, TASK_2)
    assert tree.text(ORCH) == settled
    assert _surface_changes(report) == [(row, "")]
    _assert_settled(tree)


def test_a_delegated_orchestration_lists_plan_files_only(tree):
    tree.write_back(TASK_1, TASK_2)
    for text in (tree.files[ORCH], tree.text(ORCH)):
        section = text.split("## Required Context Files", 1)[1].split("\n---", 1)[0]
        assert re.findall(r"^\| \d \| `([^`]+)` \|", section, re.MULTILINE) == [
            "QZX-Master-Plan.md", "QZX-S01-01-Recovery.md"]
    assert sp.unmasked_braces(tree.files[ORCH]) == []
    assert sp.check_headings([tree.plan / ORCH], TEMPLATES)[0]["stray"] == []
