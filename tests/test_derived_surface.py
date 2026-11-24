"""Tests for the derived session surface: rendered by scaffold_plan, priced by token_saver_writeback.

Every fixture is the real renderer's output, written to a project under tmp_path and priced by the
real write-back. No surface row is typed by hand.
"""

import json
import re
import shutil
import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import estimate_reconcile as er
import lint_gate_checks_layers as layers
import lint_verification_gates
import plan_build as pb
import scaffold_plan as sp
import token_saver_scan as tss
import token_saver_writeback as tsw
from test_plan_build import Build, bodies_set

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
                   [_row("./src/orchard/ledger.py", 3.0), _row("docs/guide.md", 0.8),
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

    def __init__(self, base, eol="\n", spec=None):
        self.root = base / "project"
        self.plan = self.root / "plans/QZX"
        for rel, text in (("src/orchard/ledger.py", "ledger = {}\n" * 900), ("docs/guide.md", "A rule.\n" * 300),
                          ("docs/other.md", "Other.\n" * 200)):
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(text.encode("utf-8"))
        self.files = sp.render_all(spec or make_spec(), TEMPLATES, project_root=self.root)[0]
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


def test_a_file_below_an_output_folder_keeps_its_own_role(tmp_path):
    spec = make_spec()
    first, second = spec["sprints"][0]["sessions"][0]["tasks"]
    first["outputs"], second["outputs"] = ["src/orchard/"], ["Outputs/QZX-index.md"]
    tree = Tree(tmp_path, spec=spec)
    for step in ("render", "write-back"):
        if step == "write-back":
            tree.write_back(TASK_1, TASK_2)
        rows = _rows(tree.text(ORCH))
        assert [rows[p][0] for p in (LEDGER, PARSE, "docs/guide.md")] == ["EDIT", CREATE, "READ"], step
        roles = []
        for cell in ("ledger.py` lines 1-10", f"`{PARSE}`"):
            row = next(ln for ln in tree.text(TASK_1).split("\n") if ln.startswith("|") and cell in ln)
            roles.append(sp.split_row_cells(row)[4].strip())
        assert roles == ["EDIT", CREATE], step


def test_the_lead_names_what_the_block_lists(tmp_path):
    spec = make_spec()
    spec["sprints"][0]["sessions"][0]["tasks"][0]["outputs"].append("src/orchard/unread.py")  # no row names it
    tree = Tree(tmp_path, spec=spec)
    lead = _block(tree.files[ORCH]).split("\n|", 1)[0]
    assert "plan files" in lead and "Required Context rows" in lead
    assert "Every file" not in lead
    tree.write_back(TASK_1, TASK_2)
    for text in (tree.files[ORCH], tree.text(ORCH)):
        assert "src/orchard/unread.py" not in _rows(text)
        assert PARSE in _rows(text)  # the control: an output a row names is listed


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
        ("Session Surface", "RuntimeError: planted"), ("Write-Set", "RuntimeError: planted")]  # both read it
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


# ---- the sprint Write-Set

PLAN = f"{SPRINT}/QZX-S01-Sprint-Plan.md"
NEW = "src/orchard/new|er.py"
QUALIFIED = f"{PARSE} (new)"


def _write_set(text):
    """[path, task, role, KiB, ~Tokens] per row, every cell filled."""
    section = text.replace("\r\n", "\n").split("\n## Write-Set", 1)[1].split("\n---\n", 1)[0]
    table = [[c.strip() for c in sp.split_row_cells(ln)] for ln in section.split("\n") if ln.startswith("|")]
    assert table[0] == ["Path", "Task", "Role", "KiB", "~Tokens"]
    assert all(len(r) == 5 and all(r) for r in table), table
    return [[r[0].strip("`"), *r[1:]] for r in table[2:]]


def _sprint_spec():
    """Task 1 writes a qualified absent file, an existing file no row cites and a folder. Two tasks write LEDGER."""
    spec = make_spec()
    first, second = spec["sprints"][0]["sessions"][0]["tasks"]
    other = spec["sprints"][0]["sessions"][1]["tasks"][0]
    first["outputs"] = [QUALIFIED, "src/orchard/calls.py", "docs/", NEW, "Outputs/QZX-parse.md"]
    second["outputs"] = [LEDGER, PARSE]
    other["outputs"] = [f"{LEDGER} (rows)", "src/orchard/calls.py"]
    return spec


@pytest.fixture
def sprint(tmp_path):
    calls = tmp_path / "project/src/orchard/calls.py"
    calls.parent.mkdir(parents=True)
    calls.write_bytes(b"call = 1\n" * 1500)
    return Tree(tmp_path, spec=_sprint_spec())


def _check_59(tree):
    return [f for f in lint_verification_gates.lint_plan(tree.plan, execute=False) if f["check"] == 59]


def test_a_write_set_row_carries_the_measured_size_or_the_flagged_estimate(sprint):
    seed = {(r[0], r[1]): r[2:] for r in _write_set(sprint.files[PLAN])}
    # The seed: 20 minus (1.5 + 0.4 + 0.7 + 0.3) is 17.1, over the folder and the new file.
    assert seed[("docs/", "QZX-S01-01-01")][2] == seed[(NEW, "QZX-S01-01-01")][2] == "~8.6K"
    sprint.write_back(TASK_1, TASK_2, OTHER_TASK)
    rows = {(r[0], r[1]): r[2:] for r in _write_set(sprint.text(PLAN))}
    size = (sprint.root / "src/orchard/calls.py").stat().st_size
    want = [sp._fmt_k(sp.estimate_tokens(size, m, "code")) for m in ("haiku", "sonnet")]
    assert Decimal(want[0].strip("~K")) < Decimal(want[1].strip("~K"))  # the control: the Agents differ
    for task in ("QZX-S01-01-01", "QZX-S01-02-01"):  # the higher price of the two Agents, on both rows
        assert rows[("src/orchard/calls.py", task)] == ["EDIT", sp._fmt_kib(size), want[1]]
    # The ~2K output addend over the two rows that reach the last step.
    kib = sp._fmt_kib(1000 * tsw.bytes_per_token("haiku", "code"))
    assert rows[(NEW, "QZX-S01-01-01")] == [CREATE, kib, "~1.0K"]
    assert rows[("docs/", "QZX-S01-01-01")][0::2] == ["EDIT (plan-time estimate)", "~1.0K"]
    # An absent path that a row cites keeps the row's plan-time figure, in both spellings.
    for path, task in ((QUALIFIED, "QZX-S01-01-01"), (PARSE, "QZX-S01-01-02")):
        assert rows[(path, task)] == [CREATE, "1.4", "~0.7K"]
    # The file lands: the figure moves and the Role cell stays.
    (sprint.root / PARSE).write_bytes(b"parse = 1\n" * 4000)
    sprint.write_back(TASK_1, TASK_2)
    for row in _write_set(sprint.text(PLAN)):
        if row[0] in (QUALIFIED, PARSE):
            assert row[2:] == [CREATE, *_task_figure(sprint.text(TASK_1), f"`{PARSE}`")]
            assert row[4] != "~0.7K"


def test_a_row_without_a_figure_prints_zero_and_one_without_an_addend_keeps_its_seed(sprint):
    sprint.set(TASK_1, sprint.text(TASK_1).replace("K (output", "K (written"))
    seeded = [r for r in _write_set(sprint.text(PLAN)) if r[0] == NEW]
    sprint.write_back(TASK_1, TASK_2)
    assert [r for r in _write_set(sprint.text(PLAN)) if r[0] == NEW] == seeded
    text = sprint.text(PLAN)
    sprint.set(PLAN, text.replace(f"| {seeded[0][3]} | {seeded[0][4]} |", "|  | ~? |"))
    sprint.write_back(TASK_1, TASK_2)
    assert [r[3:] for r in _write_set(sprint.text(PLAN)) if r[0] == NEW] == [["0.0", "~0.0K"]]


def test_the_sprint_role_is_what_role_for_returns(tmp_path):
    spec = make_spec()
    sprint, session = spec["sprints"][0], spec["sprints"][0]["sessions"][0]
    task = session["tasks"][0]
    task["outputs"] = [LEDGER, "src/orchard/absent.py", "src/orchard", "src/orchard/below.py", f"{LEDGER} (helpers)"]
    tree = Tree(tmp_path, spec=spec)
    rows = [r for r in _write_set(tree.files[PLAN]) if r[1] == "QZX-S01-01-01"]
    assert [r[0] for r in rows] == task["outputs"]
    roles = [r[2].split()[0] for r in rows]
    assert roles == [sp.role_for(r[0], task, sprint, session, tree.root) for r in rows]
    assert roles == ["EDIT", "CREATE", "EDIT", "CREATE", "EDIT"]


def test_a_path_two_tasks_cite_carries_the_higher_figure_on_every_row(sprint):
    for step in ("render", "write-back"):
        if step == "write-back":
            sprint.write_back(TASK_1, TASK_2, OTHER_TASK)
        want = list(_task_figure(sprint.text(TASK_2), "ledger.py`"))
        low = _task_figure(sprint.text(TASK_1), "ledger.py` lines 1-10")
        assert Decimal(low[1].strip("~K")) < Decimal(want[1].strip("~K"))
        rows = [r[3:] for r in _write_set(sprint.text(PLAN)) if r[0].startswith(LEDGER)]
        assert rows == [want, want], step


def test_check_59_passes_on_the_rendered_sprint_plan(sprint):
    assert _check_59(sprint) == []
    sprint.write_back(TASK_1, TASK_2, OTHER_TASK)
    assert _check_59(sprint) == []
    sprint.set(PLAN, sprint.text(PLAN).replace("| `src/orchard/calls.py` |", "| `src/other.py` |"))
    assert _check_59(sprint)  # the control: the check reads these rows


@pytest.mark.parametrize("eol", ["\n", "\r\n"], ids=["lf", "crlf"])
def test_a_second_write_back_of_the_sprint_plan_changes_no_byte(tmp_path, eol):
    spec = _sprint_spec()
    # The plan prices itself and a plan file that the same run rewrites.
    spec["sprints"][0]["sessions"][0]["tasks"][0]["outputs"] += [f"plans/QZX/{PLAN}", f"plans/QZX/{OTHER_ORCH}"]
    tree = Tree(tmp_path, eol, spec=spec)
    assert any(p.endswith("Sprint-Plan.md") for p in tree.write_back(TASK_1, OTHER_TASK)["written"])
    before = tree.snapshot()
    for names in ((TASK_1, OTHER_TASK), (OTHER_TASK,)):
        report = tree.write_back(*names)
        assert (report["written"], report["changes"], report["unreadable"]) == ([], [], [])
    assert tree.snapshot() == before
    rows = {Path(r[0]).name: r for r in _write_set(tree.text(PLAN))}
    for rel in (PLAN, OTHER_ORCH):
        assert rows[Path(rel).name][3] == sp._fmt_kib((tree.plan / rel).stat().st_size)


def test_an_old_write_set_table_is_left_as_it_is(sprint):
    lines = sprint.text(PLAN).split("\n")
    head = lines.index("| Path | Task | Role | KiB | ~Tokens |")
    end = next(i for i in range(head, len(lines)) if not lines[i].startswith("|"))
    for i in range(head, end):
        lines[i] = "| " + " | ".join(c.strip().replace("|", "\\|") for c in sp.split_row_cells(lines[i])[:2]) + " |"
    table = lines[head:end]
    sprint.set(PLAN, "\n".join(lines))
    report = sprint.write_back(TASK_1, TASK_2, OTHER_TASK)
    assert report["unreadable"] == []
    assert not [r for r in report["left"] if "Sprint-Plan" in r["file"]]
    assert any(p.endswith("Sprint-Plan.md") for p in report["written"])  # the control: the totals moved
    assert "\n".join(table) in sprint.text(PLAN)
    assert _check_59(sprint) == []


# ---- the master Write-Sets and total

MASTER = "QZX-Master-Plan.md"
PLAN_2 = "Sprint-02-LedgerExtras/QZX-S02-Sprint-Plan.md"
TASK_S2 = "Sprint-02-LedgerExtras/Session-01-Extras/QZX-S02-01-01-Opus-ExtraRows.md"


def _master(text):
    """({sprint: [Count, KiB, ~Tokens]}, total line) of the Master Plan."""
    section = text.replace("\r\n", "\n").split("\n### Write-Sets", 1)[1].split("\n### ", 1)[0]
    table = [[c.strip() for c in sp.split_row_cells(ln)] for ln in section.split("\n") if ln.startswith("|")]
    assert all(len(r) == len(table[0]) and all(r) for r in table), table
    return ({r[0]: r[2:] for r in table[2:]},
            next(ln for ln in section.split("\n") if ln.startswith("**Write-set total:**")))


def _two_sprints():
    """Sprint two writes LEDGER, as sprint one does, under a second spelling. Sprint one writes PARSE in two spellings."""
    spec = _sprint_spec()
    extra = _task(1, "ExtraRows", "Opus", [f"{LEDGER} (extras)", "src/orchard/extra.py"], [_row(LEDGER, 9.0)])
    spec["sprints"].append({"number": 2, "name": "LedgerExtras", "purpose": "Extend the core", "sessions": [
        {"number": 1, "name": "Extras", "objective": "Extend", "mode": "DIRECT", "prerequisite": "The core",
         "tasks": [extra]}]})
    spec["sprints"].append({"number": 3, "name": "Empty", "purpose": "Report", "sessions": [
        {"number": 1, "name": "Report", "objective": "Report", "mode": "DIRECT", "prerequisite": "The extras",
         "tasks": [_task(1, "Report", "Opus", ["Outputs/QZX-report.md"], [_row("docs/guide.md", 0.8)])]}]})
    return spec


def _expected(*plans):
    """(Count, KiB, ~Tokens) over the plans' rows: a path once at its highest figure. Every qualifier here ends in `)`."""
    best = {}
    for text in plans:
        for path, _task_cell, _role, kib, tokens in _write_set(text):
            key, figure = re.sub(r" \(.*\)$", "", path), Decimal(tokens.strip("~K"))
            if key not in best or figure > best[key][1]:
                best[key] = (Decimal(kib.replace(",", "")), figure)
    kib, tokens = (sum(f[i] for f in best.values()) for i in (0, 1))
    return [str(len(best)), f"{kib:,}", f"~{tokens}K"]


def _assert_master(tree):
    rows, total = _master(tree.text(MASTER))
    one, two = _expected(tree.text(PLAN)), _expected(tree.text(PLAN_2))
    both = _expected(tree.text(PLAN), tree.text(PLAN_2))
    assert rows == {"Sprint-01": one, "Sprint-02": two, "Sprint-03": ["0", "0.0", "~0.0K"]}
    assert total == f"**Write-set total:** {both[2]} tokens over {both[0]} distinct paths (information only)"
    assert int(both[0]) == int(one[0]) + int(two[0]) - 1  # the control: the sprints share LEDGER
    return one, two, both


def test_the_master_total_counts_each_path_once_and_follows_a_changed_figure(tmp_path):
    tree = Tree(tmp_path, spec=_two_sprints())
    one, two, both = _assert_master(tree)
    assert (one[0], two[0], both[0]) == ("5", "2", "6")  # eight rows of sprint one, with three respellings
    tree.write_back(TASK_1, TASK_2, OTHER_TASK, TASK_S2)
    settled = _assert_master(tree)
    assert settled[2] != both
    (tree.root / LEDGER).write_bytes(b"ledger = {}\n" * 9000)
    tree.write_back(TASK_2)  # sprint two is not named, so its row keeps its Sprint Plan's present cells
    moved = _assert_master(tree)
    assert moved[1] == settled[1] and moved[2] != settled[2]


@pytest.mark.parametrize("eol", ["\n", "\r\n"], ids=["lf", "crlf"])
def test_a_second_write_back_of_the_master_plan_changes_no_byte(tmp_path, eol):
    spec = _two_sprints()
    # A Write-Set row prices the Master Plan, whose own cells change its size.
    spec["sprints"][0]["sessions"][0]["tasks"][0]["outputs"].append(f"plans/QZX/{MASTER}")
    tree = Tree(tmp_path, eol, spec=spec)
    # With a long cell the file is larger, so one pass would price the Master Plan's row too high.
    text = tree.text(MASTER)
    kib = _master(text)[0]["Sprint-02"][1]
    tree.set(MASTER, text.replace(f"| 2 | {kib} |", f"| 2 | {'9' * 400} |"))
    assert len(tree.text(MASTER)) > len(text) + 300
    names = (TASK_1, TASK_2, OTHER_TASK, TASK_S2)
    report = tree.write_back(*names)
    assert any(p.endswith(MASTER) for p in report["written"])
    assert report["unreadable"] == []
    before = tree.snapshot()
    report = tree.write_back(*names)
    assert (report["written"], report["changes"], report["unreadable"]) == ([], [], [])
    assert tree.snapshot() == before
    own = next(r for r in _write_set(tree.text(PLAN)) if r[0].endswith(MASTER))
    assert own[3] == sp._fmt_kib((tree.plan / MASTER).stat().st_size)
    data = (tree.plan / MASTER).read_bytes()
    assert data.count(b"\r\n") == (data.count(b"\n") if eol == "\r\n" else 0)


@pytest.mark.parametrize("gap", ["plan", "table", "row", "total", "columns", "master"])
def test_a_missing_part_of_the_master_grain_is_silent(tmp_path, gap):
    tree = Tree(tmp_path, spec=_two_sprints())
    rows, total = _master(tree.text(MASTER))
    master = tree.text(MASTER)
    if gap == "plan":
        (tree.plan / PLAN_2).unlink()
    elif gap == "table":
        tree.set(PLAN_2, tree.text(PLAN_2).replace("| Path | Task | Role | KiB | ~Tokens |", "| Path | Task | Role | A | B |"))
    elif gap == "row":
        tree.set(MASTER, "\n".join(ln for ln in master.split("\n") if not ln.startswith("| Sprint-02 | `")))
    elif gap == "total":
        tree.set(MASTER, master.replace(total + "\n", ""))
    elif gap == "columns":
        tree.set(MASTER, master.replace("| Sprint | Write-set | Count |", "| Sprint | Write-set | Size |"))
    else:
        (tree.plan / MASTER).unlink()
    report = tree.write_back(TASK_1, TASK_2, OTHER_TASK)
    assert report["unreadable"] == []
    assert not [r for r in report["left"] if "Master" in r["file"]]
    if gap == "master":
        assert not (tree.plan / MASTER).exists()
        return
    text = tree.text(MASTER)
    assert (total in text) == (gap in ("plan", "table"))
    assert ("**Write-set total:**" in text) == (gap != "total")
    assert ("| Sprint-01 | " in text and rows["Sprint-01"][2] in text) == (gap == "columns")
    if gap in ("plan", "table"):
        assert _master(text)[0]["Sprint-02"] == rows["Sprint-02"]


# One literal header per grain, copied from the surface contract. A change there updates this table.
HEADERS = {
    "task": "| Priority | File | KiB | ~Tokens | Role | Purpose |",
    "session": "| Path | Role | KiB | ~Tokens | Cited By |",
    "sprint": "| Path | Task | Role | KiB | ~Tokens |",
    "master": "| Sprint | Write-set | Count | KiB | ~Tokens |",
    "master total": "**Write-set total:** ~{T}K tokens over {F} distinct paths (information only)",
}


def test_every_grain_renders_the_contract_header(tmp_path):
    files = Tree(tmp_path, spec=_two_sprints()).files
    places = {"task": (TASK_1, "## Required Context", "|"), "session": (ORCH, "## Session Surface", "|"),
              "sprint": (PLAN, "## Write-Set", "|"), "master": (MASTER, "### Write-Sets", "|"),
              "master total": (MASTER, "### Write-Sets", "**Write-set total:**")}
    got = {}
    for grain, (rel, heading, start) in places.items():
        section = files[rel].split(f"\n{heading}", 1)[1]
        line = next(ln for ln in section.split("\n") if ln.startswith(start))
        got[grain] = re.sub(r"over \d+ ", "over {F} ", re.sub(r"~[\d.]+K", "~{T}K", line))
    assert got == HEADERS


OLD_TASK = """# Task: Probe

**Task ID:** QZX-S01-01-01
**Agent:** Sonnet
**Estimated Tokens:** ~10K
**Output:** `src/orchard/ledger.py`

---

## Required Context

| Priority | File | KiB | ~Tokens | Purpose |
|----------|------|----:|--------:|---------|
| 1 | `src/orchard/ledger.py` | 9.9 | ~4.0K | the module |
| 2 | `QZX-S01-01-01-Sonnet-Probe.md` | 1.0 | ~0.4K | this task file |

**Context subtotal:** ~4.4K (reads) + ~5K (output) + ~1K (working) = **~10K total**

---

## Execution Steps

1. Do the thing.
"""
OLD_ORCH = """# Orchestration

## Session Task List

| # | Task | Agent | Est. Tokens | Depends On |
|---|------|-------|-------------|------------|
| 1 | Probe: price the ledger | Sonnet | ~10K | - |

**Total Estimated:** ~10K tokens

## Dispatch Layers

**Declared layers:** L1 = {1}
"""
OLD_SPRINT = """# Sprint Plan

**Estimated Tokens:** ~10K total across all sessions

## Sessions

| Session | ID | Name | Objective | Est. Tokens |
|---------|----|------|-----------|-------------|
| 1 | QZX-S01-01 | ReadPath | Price the ledger | ~10K |

## Write-Set

| Path | Task |
|------|------|
| `src/orchard/ledger.py` | QZX-S01-01-01 |

## Session Details

### Session 01: ReadPath (QZX-S01-01)

| # | Task | Agent | Est. Tokens | Depends On |
|---|------|-------|-------------|------------|
| 1 | Probe: price the ledger | Sonnet | ~10K | - |

**Total Estimated:** ~10K tokens
"""
OLD_MASTER = """# OrchardLedger Master Plan

## Execution Ordering

### Write-Sets

| Sprint | Write-set |
|--------|-----------|
| Sprint-01 | `src/orchard/ledger.py` |

### Computed Write-Set Intersection

| Declared pair | Intersection | Verdict |
|---------------|--------------|---------|
| none declared | n/a | serial order |
"""


def test_a_whole_plan_in_the_old_shape_stays_in_the_old_shape(tmp_path, capsys):
    plan = tmp_path / "plans/QZX"
    old = {f"{READ_PATH}/QZX-S01-01-01-Sonnet-Probe.md": OLD_TASK, ORCH: OLD_ORCH, PLAN: OLD_SPRINT,
           RECOVERY: "# Recovery\n", MASTER: OLD_MASTER}
    for rel, text in {LEDGER: "ledger = {}\n" * 900, **{f"plans/QZX/{r}": t for r, t in old.items()}}.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
    task = plan / READ_PATH / "QZX-S01-01-01-Sonnet-Probe.md"
    for rel in (ORCH, PLAN):  # stale totals, so the write-back has work in each file
        text = old[rel] = old[rel].replace("~10K", "~12K")
        (plan / rel).write_bytes(text.encode("utf-8"))
    report = tsw.write_estimates([task], plan, tmp_path)
    assert (report["errors"], report["unreadable"], report["left"]) == ([], [], [])
    assert {Path(p).name for p in report["written"]} == {Path(r).name for r in old} - {MASTER, Path(RECOVERY).name}
    for rel, text in old.items():
        after = (plan / rel).read_bytes().decode("utf-8")
        shape = [[len(sp.split_row_cells(ln)) if ln.startswith("|") else ln.startswith("#") and ln
                  for ln in t.split("\n") if ln.startswith(("|", "#"))] for t in (text, after)]
        assert shape[0] == shape[1], rel  # no new column, row or heading
        for name in ("Session Surface", "Role |", "| Count |", "**Write-set total:**", "**Session surface:**"):
            assert name not in after, rel
    assert (plan / MASTER).read_bytes().decode("utf-8") == OLD_MASTER
    result = tss.scan_plan(plan, {"context": {"token_saver": True}}, tmp_path)
    assert (result["summary"]["tasks"], result["summary"]["files"]) == (1, 2)  # the control: the scan read the rows
    assert (result["findings"], result["unresolved"], result["over_ceiling"]) == ([], [], [])
    capsys.readouterr()
    code = er.main(["check", str(plan)])
    out = capsys.readouterr().out.splitlines()
    assert code == 0, out
    assert out[-1] == "estimates: sessions=1 mismatches=0 unread=0"


# ---- edge cases of the Write-Set readers and writers

def test_a_sprint_with_no_write_path_prints_one_derived_row(tmp_path):
    tree = Tree(tmp_path, spec=_two_sprints())
    rel = "Sprint-03-Empty/QZX-S03-Sprint-Plan.md"
    task = "Sprint-03-Empty/Session-01-Report/QZX-S03-01-01-Opus-Report.md"
    for step in ("render", "write-back"):
        if step == "write-back":
            assert tree.write_back(TASK_1, task)["unreadable"] == []
        assert _write_set(tree.text(rel)) == [["none", "n/a", "n/a", "0.0", "~0.0K"]], step
        assert layers._write_set_rows(tree.text(rel).split("\n")) == []  # what Check 59 reads
        assert _master(tree.text(MASTER))[0]["Sprint-03"] == ["0", "0.0", "~0.0K"]


def test_a_parenthesis_inside_a_path_is_part_of_the_name(tmp_path):
    spec = _two_sprints()
    spec["sprints"][0]["sessions"][0]["tasks"][0]["outputs"] = ["app/(shop)/", "app/", "app/:10"]
    tree = Tree(tmp_path, spec=spec)
    assert _master(tree.files[MASTER])[0]["Sprint-01"][0] == "6"  # three here, then LEDGER, PARSE and calls.py
    rows = [r[0] for r in _write_set(tree.files[PLAN])]
    assert rows[:3] == ["app/(shop)/", "app/", "app/:10"]
    (tree.root / "docs/other.md(2)").write_bytes(b"Two.\n")
    _add_rows(tree, "`docs/guide.md(2)`", "`docs/guide.md (2)`", "`docs/other.md(2)`")
    tree.write_back(TASK_1, TASK_2)
    assert not {"docs/guide.md(2)", "docs/guide.md (2)"} & set(_rows(tree.text(ORCH)))  # a qualifier drops
    assert "docs/other.md(2)" in _rows(tree.text(ORCH))  # the control: a file of that name


@pytest.mark.parametrize("shape", ["old", "new"])
def test_an_undecodable_sprint_plan_never_blocks_the_other_writes(sprint, shape):
    sprint.set(ORCH, sprint.text(ORCH).replace("| 2 | IndexRows: ", "| 9 | IndexRows: "))
    text = sprint.text(PLAN)
    if shape == "old":
        text = text.replace("| Path | Task | Role | KiB | ~Tokens |", "| Path | Task | Role | A | B |")
    data = text.encode("utf-8") + b"\n\xff cp1252\n"
    (sprint.plan / PLAN).write_bytes(data)
    report = sprint.write_back(TASK_1, TASK_2)
    assert Path(TASK_1).name in {Path(p).name for p in report["written"]}
    whats = [u["what"] for u in report["unreadable"]]
    assert whats == ["task row QZX-S01-01-02"] + (["Write-Set"] if shape == "new" else [])
    assert (sprint.plan / PLAN).read_bytes() == data


def test_a_row_that_names_no_path_keeps_its_cells_and_takes_no_share(sprint):
    text = sprint.text(PLAN)
    row = next(ln for ln in text.split("\n") if ln.startswith("| `docs/` |"))
    bare = ["| none | QZX-S01-01-01 | n/a | n/a | n/a |", "| `none (reads only)` | QZX-S01-01-01 | READ | 0.0 | ~0.0K |"]
    sprint.set(PLAN, text.replace(row, "\n".join([row, *bare])))
    sprint.write_back(TASK_1, TASK_2, OTHER_TASK)
    after = sprint.text(PLAN)
    assert all(b in after.split("\n") for b in bare)
    # The ~2K output addend still splits over the two rows that name a path.
    assert {r[0]: r[4] for r in _write_set(after) if r[0] in ("docs/", NEW)} == {"docs/": "~1.0K", NEW: "~1.0K"}


@pytest.mark.parametrize("form", ["~2K (output)", "~2K output", "~2K (output: one file)"])
def test_every_addend_form_gives_the_output_share(sprint, form):
    text = sprint.text(TASK_1)
    assert "+ ~2K (output)" in text
    sprint.set(TASK_1, text.replace("+ ~2K (output)", f"+ {form}"))
    sprint.write_back(TASK_1, TASK_2, OTHER_TASK)
    assert [r[4] for r in _write_set(sprint.text(PLAN)) if r[0] == NEW] == ["~1.0K"]


def test_a_task_whose_name_holds_orchestration_is_a_task(tmp_path):
    spec = _two_sprints()
    first, second = spec["sprints"][0]["sessions"][0]["tasks"]
    second["name"] = "OrchestrationRows"
    name = "QZX-S01-01-02-Opus-OrchestrationRows.md"
    second["outputs"] = [LEDGER]
    first["outputs"] = [LEDGER, name, f"plans/QZX/{READ_PATH}/{name}"]
    tree = Tree(tmp_path, spec=spec)
    count = _master(tree.files[MASTER])[0]["Sprint-01"][0]
    rel = f"{READ_PATH}/{name}"
    assert tree.write_back(TASK_1, rel)["unreadable"] == []
    want = _task_figure(tree.text(rel), "ledger.py`")
    assert want[1] != "~3.0K"  # the control: the write-back moved the figure
    assert {tuple(r[3:]) for r in _write_set(tree.text(PLAN)) if r[0] == LEDGER} == {want}
    assert _master(tree.text(MASTER))[0]["Sprint-01"][0] == count == "3"  # LEDGER, the task file, calls.py


def test_two_spellings_of_one_file_are_not_disjoint(tmp_path):
    spec = _two_sprints()
    spec["parallel_pairs"] = [[1, 2], [2, 1], [1, 3]]
    section = Tree(tmp_path, spec=spec).files[MASTER].split("### Computed Write-Set Intersection", 1)[1]
    rows = [[c.strip() for c in sp.split_row_cells(ln)] for ln in section.split("\n") if ln.startswith("| Sprint-")][:3]
    assert [r[1] for r in rows] == [f"`{LEDGER}`", f"`{LEDGER} (extras)`", "∅"]
    assert ["NOT" in r[2] for r in rows] == [True, True, False]


ZZ = f"{READ_PATH}/Outputs/zz.md"


@pytest.mark.parametrize("first,second,same", [
    (f"plans/QZX/{ZZ}", f"plans/QZX/{ZZ}", True),
    (ZZ, f"plans/QZX/{ZZ}", True),
    (f"plans/QZX/{ZZ}", ZZ, True),
    (ZZ, ZZ, True),
    (f"plans/QZX/{ZZ}", f"plans/ABC/{ZZ}", False),
    ("{planwise_root}/new.md", "planwise/new.md", True),
    ("src/orchard/new.py(a)", "src/orchard/new.py", True),
])
def test_two_parallel_sprints_share_a_file_under_any_spelling(tmp_path, first, second, same):
    spec = _two_sprints()
    spec["parallel_pairs"] = [[1, 2]]
    sprints = [se["tasks"][0] for s in spec["sprints"][:2] for se in s["sessions"][:1]]
    for task, output in zip(sprints, (first, second)):
        task["outputs"] = [output]
    for task in (spec["sprints"][0]["sessions"][0]["tasks"][1], spec["sprints"][0]["sessions"][1]["tasks"][0]):
        task["outputs"] = ["Outputs/QZX-b.md"]
    tree = Tree(tmp_path, spec=spec)
    for step in ("render", "write-back"):
        if step == "write-back":
            assert tree.write_back(TASK_1, TASK_S2)["unreadable"] == []
        text = tree.text(MASTER)
        row = next(ln for ln in text.split("\n") if ln.startswith("| Sprint-01 ∥ Sprint-02"))
        assert (f"| `{first}` |" in row, "NOT" in row) == (same, same)
        assert f"over {1 if same else 2} distinct paths" in _master(text)[1], step


def test_an_output_cited_in_full_keeps_its_cited_figure(tmp_path):
    spec = _two_sprints()
    first, second = spec["sprints"][0]["sessions"][0]["tasks"]
    first["outputs"] = second["outputs"] = [f"plans/QZX/{ZZ}"]
    first["required_context"].append(_row("Outputs/zz.md", 4.4))
    tree = Tree(tmp_path, spec=spec)
    for step in ("render", "write-back"):
        if step == "write-back":
            tree.write_back(TASK_1, TASK_2)
        assert [r[4] for r in _write_set(tree.text(PLAN)) if r[0].endswith("zz.md")] == ["~4.4K"] * 2, step


def test_a_bare_name_is_one_path_whichever_session_names_it(tmp_path):
    spec = _two_sprints()
    for s in spec["sprints"][:2]:
        for task in (t for se in s["sessions"] for t in se["tasks"]):
            task["outputs"] = ["notes.md"]
    tree = Tree(tmp_path, spec=spec)
    for rel in (TASK_1, TASK_S2):
        (tree.plan / rel).with_name("notes.md").write_bytes(b"Notes.\n")
    tree.write_back(TASK_1, TASK_S2)
    assert "over 1 distinct paths" in _master(tree.text(MASTER))[1]


def _rename(tree, rel, name):
    path = tree.plan / rel
    path.rename(path.with_name(name))
    return f"{Path(rel).parent.as_posix()}/{name}"


def test_a_task_named_exactly_orchestration_is_a_task(tmp_path):
    spec = _two_sprints()
    second = spec["sprints"][0]["sessions"][0]["tasks"][1]
    second["name"], second["outputs"] = "Orchestration", [LEDGER]
    tree = Tree(tmp_path, spec=spec)
    rel = f"{READ_PATH}/QZX-S01-01-02-Opus-Orchestration.md"
    report = tree.write_back(TASK_1, rel)
    assert report["unreadable"] == [] and any(p.endswith(Path(ORCH).name) for p in report["written"])
    want = _task_figure(tree.text(rel), "ledger.py`")
    assert want[1] != "~3.0K"  # the control: the write-back moved the figure
    assert {tuple(r[3:]) for r in _write_set(tree.text(PLAN)) if r[0] == LEDGER} == {want}


@pytest.mark.parametrize("name", ["Orchestration.md", "QZX-S01-01-Orchestration-v2.md"])
@pytest.mark.parametrize("task", ["IndexRows", "Orchestration"])
def test_one_loosely_named_orchestration_is_still_rolled(tmp_path, name, task):
    spec = _two_sprints()
    spec["sprints"][0]["sessions"][0]["tasks"][1]["name"] = task
    tree = Tree(tmp_path, spec=spec)
    rel = _rename(tree, ORCH, name)
    report = tree.write_back(TASK_1, f"{READ_PATH}/QZX-S01-01-02-Opus-{task}.md")
    assert report["unreadable"] == [] and any(Path(p).name == name for p in report["written"])
    (tree.plan / rel).with_name("QZX-Orchestration-old.md").write_bytes(b"# Old\n")
    report = tree.write_back(TASK_1)
    assert [(u["what"], u["reason"]) for u in report["unreadable"]] == [
        ("Orchestration", "2 files match *-Orchestration.md")]


@pytest.mark.parametrize("name", tsw._TOKEN_HEADERS)
def test_every_token_header_gets_the_token_cell_and_an_unknown_one_prints_na(tmp_path, name):
    templates = tmp_path / "t"
    shutil.copytree(TEMPLATES, templates)
    plain = sp.render_all(_two_sprints(), TEMPLATES, project_root=tmp_path)[0]
    for file, start in (("sprint-plan.md", "| Path | Task |"), ("master-plan.md", "| Sprint | Write-set |")):
        lines = (templates / file).read_text(encoding="utf-8").split("\n")
        head = next(i for i, ln in enumerate(lines) if ln.startswith(start))
        lines[head] = lines[head].replace("~Tokens", name.title()) + " Owner |"
        for i, cell in ((1, "---"), (2, "{Owner}"), (3, "{Owner}")):
            lines[head + i] += f" {cell} |"
        (templates / file).write_text("\n".join(lines), encoding="utf-8")
    files = sp.render_all(_two_sprints(), templates, project_root=tmp_path)[0]
    for rel, start in ((PLAN, "| `src/"), (PLAN_2, "| `src/"), (MASTER, "| Sprint-01 | `"), (MASTER, "| Sprint-03 | none")):
        want, got = ([ln for ln in fs[rel].split("\n") if ln.startswith(start)] for fs in (plain, files))
        assert want and got == [f"{ln} n/a |" for ln in want]


# ---- a cited file that the same run resizes

ALL_TASKS = (TASK_1, TASK_2, OTHER_TASK, TASK_S2)
EOLS = pytest.mark.parametrize("eol", ["\n", "\r\n"], ids=["lf", "crlf"])
# The row whose KiB cell each cited file re-prices, so a long cell there is a file that this run shrinks.
PRICED_ROW = {MASTER: "| Sprint-02 | `", PLAN: "| `src/orchard/calls.py` |", PLAN_2: "| `src/orchard/extra.py` |",
              ORCH: "| `docs/guide.md` |", TASK_2: "| 1 | `docs/guide.md` |"}


def _citing(tmp_path, *cells, eol="\n"):
    spec = _two_sprints()
    spec["sprints"][0]["sessions"][0]["tasks"][0]["required_context"] += [_row(c, 1.0) for c in cells]
    return Tree(tmp_path, eol, spec=spec)


def _lengthen(tree, rel, digits=400):
    """Give one derived KiB cell of `rel` a long figure."""
    text = tree.text(rel)
    row = next(ln for ln in text.split("\n") if ln.startswith(PRICED_ROW[rel]))
    parts = row.split("|")
    at = next(i for i, p in enumerate(parts) if re.fullmatch(r" [\d.,]+ ", p) and "." in p)
    parts[at] = f" {'9' * digits} "
    tree.set(rel, text.replace(row, "|".join(parts)))
    assert len(tree.text(rel)) > len(text) + digits - 20


def _assert_stable(tree, *names):
    before = tree.snapshot()
    report = tree.write_back(*names)
    assert (report["written"], report["changes"], report["unreadable"]) == ([], [], [])
    assert tree.snapshot() == before


def _assert_one_record_each(report):
    for key, fields in (("changes", ("file", "line", "what")), ("spans", ("file", "row")), ("left", ("file", "row"))):
        seen = [tuple(item[f] for f in fields) for item in report[key]
                if not (key == "changes" and item["what"] in ("Session Surface", "Estimated Tokens"))]
        assert len(seen) == len(set(seen)), key


@EOLS
@pytest.mark.parametrize("pad", [0, 13, 38, 51, 77, 102])
def test_a_cited_master_plan_settles_over_every_padding(tmp_path, eol, pad):
    tree = _citing(tmp_path, f"plans/QZX/{MASTER}", eol=eol)
    tree.set(MASTER, tree.text(MASTER) + "x" * pad)
    report = tree.write_back(*ALL_TASKS)
    assert report["unreadable"] == [] and any(p.endswith(MASTER) for p in report["written"])
    _assert_one_record_each(report)
    _assert_stable(tree, *ALL_TASKS)
    want = sp._fmt_kib((tree.plan / MASTER).stat().st_size)
    assert _task_figure(tree.text(TASK_1), MASTER)[0] == _rows(tree.text(ORCH))[f"plans/QZX/{MASTER}"][1] == want


@EOLS
@pytest.mark.parametrize("rel", [MASTER, PLAN, ORCH, TASK_2], ids=["master", "sprint", "orchestration", "task"])
def test_a_cited_file_that_the_run_shrinks_settles(tmp_path, eol, rel):
    tree = _citing(tmp_path, f"plans/QZX/{rel}", eol=eol)
    _lengthen(tree, rel)
    before = (tree.plan / rel).stat().st_size
    report = tree.write_back(*ALL_TASKS)
    assert report["unreadable"] == []
    _assert_one_record_each(report)
    size = (tree.plan / rel).stat().st_size
    assert sp._fmt_kib(size) != sp._fmt_kib(before)  # the control: the run resized it
    _assert_stable(tree, *ALL_TASKS)
    assert _task_figure(tree.text(TASK_1), Path(rel).name)[0] == sp._fmt_kib(size)
    data = (tree.plan / rel).read_bytes()
    assert data.count(b"\r\n") == (data.count(b"\n") if eol == "\r\n" else 0)


@EOLS
def test_a_cited_span_of_a_file_that_the_run_rewrites_settles(tmp_path, eol):
    tree = _citing(tmp_path, eol=eol)
    _lengthen(tree, MASTER)
    last = tree.text(MASTER).count("\n")
    text = tree.text(TASK_1)
    row = next(ln for ln in text.split("\n") if ln.startswith("|") and "ledger.py` lines 1-10" in ln)
    tree.set(TASK_1, text.replace(row, row + "\n" + row.replace(LEDGER, f"plans/QZX/{MASTER}").replace("1-10", f"1-{last}")))
    report = tree.write_back(*ALL_TASKS)
    assert report["unreadable"] == []
    _assert_one_record_each(report)
    _assert_stable(tree, *ALL_TASKS)
    kept = (tree.plan / MASTER).read_bytes().split(b"\n")[:last]
    assert _task_figure(tree.text(TASK_1), MASTER)[0] == sp._fmt_kib(sum(len(ln) + 1 for ln in kept))


@EOLS
def test_a_write_set_row_of_another_sprint_plan_settles(tmp_path, eol):
    spec = _two_sprints()
    spec["sprints"][0]["sessions"][0]["tasks"][0]["outputs"].append(f"plans/QZX/{PLAN_2}")
    tree = Tree(tmp_path, eol, spec=spec)
    # No sized table and no total line, so the Master Plan does not move.
    text = tree.text(MASTER).replace("| Sprint | Write-set | Count |", "| Sprint | Write-set | Size |")
    tree.set(MASTER, text.replace("**Write-set total:**", "**Total:**"))
    _lengthen(tree, PLAN_2)
    report = tree.write_back(*ALL_TASKS)
    assert report["unreadable"] == [] and not any(p.endswith(MASTER) for p in report["written"])
    _assert_one_record_each(report)
    _assert_stable(tree, *ALL_TASKS)
    row = next(r for r in _write_set(tree.text(PLAN)) if r[0].endswith(PLAN_2))
    assert row[3] == sp._fmt_kib((tree.plan / PLAN_2).stat().st_size)


@pytest.mark.parametrize("cited,passes", [(False, 1), (True, 2)], ids=["none-cited", "cited"])
def test_the_run_repeats_only_for_a_cited_file(tmp_path, monkeypatch, cited, passes):
    tree = _citing(tmp_path, *([f"plans/QZX/{MASTER}"] if cited else []))
    read = {rel: tree.text(rel).split("\n") for rel in ALL_TASKS}
    calls, real = [], tsw._write_task
    monkeypatch.setattr(tsw, "_write_task", lambda *a: calls.append(a[2]) or real(*a))
    report = tree.write_back(*ALL_TASKS)
    assert len(calls) == passes * len(ALL_TASKS)
    _assert_one_record_each(report)
    assert sum(c["what"] == "Measured footer" for c in report["changes"]) == len(ALL_TASKS)
    for rel, lines in read.items():  # each record holds the value as read and the value as written
        after = tree.text(rel).split("\n")
        for c in report["changes"]:
            if c["file"].endswith(Path(rel).name) and c["what"].startswith("row "):
                assert c["old"] in lines[c["line"] - 1] and c["new"] in after[c["line"] - 1]


def test_a_cell_that_ends_where_it_began_moves_no_footer_date(tmp_path):
    tree = _citing(tmp_path, f"plans/QZX/{MASTER}")
    paths = [tree.plan / r for r in ALL_TASKS]
    tsw.write_estimates(paths, tree.plan, tree.root, today=tsw.date(2030, 1, 15))
    before = tree.snapshot()
    _lengthen(tree, MASTER)  # the row reads stale for one pass only
    report = tsw.write_estimates(paths, tree.plan, tree.root, today=tsw.date(2030, 2, 20))
    assert [Path(p).name for p in report["written"]] == [MASTER]
    assert {Path(c["file"]).name for c in report["changes"]} == {MASTER}
    assert tree.snapshot() == before


def _growing_master(tree, monkeypatch):
    """Make each pass append a longer line to the Master Plan than the pass before."""
    calls, real = [], tsw._write_master

    def grow(buf, *args):
        real(buf, *args)
        calls.append("x" * 200)
        buf.get(tree.plan / MASTER).append("".join(calls))

    monkeypatch.setattr(tsw, "_write_master", grow)
    return calls


def test_a_run_that_does_not_settle_writes_its_last_pass_and_reports_the_file(tmp_path, monkeypatch):
    tree = _citing(tmp_path, f"plans/QZX/{MASTER}")
    calls = _growing_master(tree, monkeypatch)
    dry = tsw.write_estimates([tree.plan / r for r in ALL_TASKS], tree.plan, tree.root, dry_run=True)
    assert dry["changes"] and not dry["written"]
    calls.clear()
    report = tree.write_back(*ALL_TASKS)
    assert len(calls) == tsw._SELF_ROW_PASSES
    assert {*ALL_TASKS, ORCH, OTHER_ORCH, PLAN, MASTER} <= {
        Path(p).relative_to(tree.plan).as_posix() for p in report["written"]}
    assert report["changes"] == dry["changes"]
    _assert_one_record_each(report)
    assert [(Path(u["file"]).name, u["what"]) for u in report["unreadable"]] == [(MASTER, "cited file")]
    assert "a later run may move the rows that cite it" in report["unreadable"][0]["reason"]
    assert "Cell changes: none" not in tsw.format_write_report(report)
    monkeypatch.undo()
    assert tree.write_back(*ALL_TASKS)["unreadable"] == []
    _assert_stable(tree, *ALL_TASKS)


@pytest.mark.parametrize("span", ["lines 1-3", "§1"])
def test_a_file_that_moves_outside_the_cited_span_is_settled(tmp_path, monkeypatch, span):
    tree = _citing(tmp_path)
    tree.set(MASTER, "# Plan\n\n## 1. Cited\n\nText.\n\n## 2. Next\n\n" + tree.text(MASTER))
    _add_rows(tree, f"`plans/QZX/{MASTER}` {span}")
    calls = _growing_master(tree, monkeypatch)
    report = tree.write_back(*ALL_TASKS)
    assert (len(calls), report["unreadable"]) == (1, [])
    assert any(s["resolved"].startswith(span.split("-")[0]) for s in report["spans"])  # the control: the span was priced
    assert report["written"]


def test_a_citation_chain_longer_than_the_pass_limit_is_written(tmp_path, monkeypatch):
    tree = _citing(tmp_path, f"plans/QZX/{MASTER}", f"plans/QZX/{PLAN}")
    for rel in (MASTER, PLAN):
        _lengthen(tree, rel)
    real = tsw.write_estimates(
        [tree.plan / r for r in ALL_TASKS], tree.plan, tree.root, dry_run=True)
    assert real["unreadable"] == []  # the control: the default limit is enough for this chain
    passes = []
    real_pass = tsw._write_pass

    def count(*args):
        passes.append(1)
        real_pass(*args)

    class Short:
        """The outer limit only: the settle loops inside one pass keep theirs."""
        def __index__(self):
            return 1 if sys._getframe(1).f_code.co_name == "write_estimates" else 6

    monkeypatch.setattr(tsw, "_write_pass", count)
    monkeypatch.setattr(tsw, "_SELF_ROW_PASSES", Short())
    report = tree.write_back(*ALL_TASKS)
    assert len(passes) == 1 and len(report["written"]) > len(ALL_TASKS)
    assert {Path(u["file"]).name for u in report["unreadable"]} == {MASTER, Path(PLAN).name}
    monkeypatch.undo()
    assert tree.write_back(*ALL_TASKS)["unreadable"] == []
    _assert_stable(tree, *ALL_TASKS)


def test_a_failed_task_keeps_its_bytes_and_blocks_no_other_file(tmp_path):
    tree = _citing(tmp_path, f"plans/QZX/{MASTER}")
    _lengthen(tree, MASTER)
    tree.set(OTHER_TASK, tree.text(OTHER_TASK).replace("**Context subtotal:**", "**Subtotal:**"))
    kept = tree.text(OTHER_TASK)
    report = tree.write_back(*ALL_TASKS)
    assert [(Path(u["file"]).name, u["what"]) for u in report["unreadable"]] == [
        (Path(OTHER_TASK).name, "Context subtotal")]
    assert not any(p.endswith(Path(OTHER_ORCH).name) for p in report["written"])
    assert {TASK_1, MASTER} <= {Path(p).relative_to(tree.plan).as_posix() for p in report["written"]}
    body = [ln for ln in kept.split("\n") if not ln.startswith(("|", "**Measured:**"))]
    assert [ln for ln in tree.text(OTHER_TASK).split("\n") if not ln.startswith(("|", "**Measured:**"))][:20] == body[:20]
    before = tree.snapshot()
    assert tree.write_back(*ALL_TASKS)["written"] == []
    assert tree.snapshot() == before


# ---- the project root of the two production callers

@pytest.fixture
def outside(tmp_path, monkeypatch):
    """(project root, its config, a spec file): the working directory is a sibling of the project."""
    root = tmp_path / "project"
    for rel, text in ((LEDGER, "ledger = {}\n"), ("docs/guide.md", "A rule.\n"),
                      ("planwise/config.yaml", "project:\n  name: Demo\nplan_statuses:\n  - 1\n")):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(text.encode("utf-8"))
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps(make_spec()), encoding="utf-8")
    (tmp_path / "elsewhere").mkdir()
    monkeypatch.chdir(tmp_path / "elsewhere")
    return root, root / "planwise/config.yaml", spec


def _ledger_role(plan):
    text = (plan / TASK_2).read_bytes().decode("utf-8").replace("\r\n", "\n")
    row = next(ln for ln in text.split("\n") if ln.startswith("|") and "ledger.py`" in ln)
    return sp.split_row_cells(row)[4].strip()


def test_plan_build_outside_the_project_reads_the_config_root(tmp_path, outside, capsys):
    _root, config, spec = outside
    (tmp_path / "b").mkdir()
    build = Build(tmp_path / "b", capsys, bodies_set(pb.render_core(str(spec), TEMPLATES)[2]), make_spec())
    build.config = config
    _code, out = build.run()
    assert "built " in out, out
    assert _ledger_role(build.out) == "EDIT"


def test_scaffold_render_outside_the_project_reads_the_config_root(tmp_path, outside):
    _root, config, spec = outside
    assert sp.main(["render", "--spec", str(spec), "--out", str(tmp_path / "plan"), "--config", str(config)]) == 0
    assert _ledger_role(tmp_path / "plan") == "EDIT"


@pytest.mark.parametrize("inside,expected", [(True, "EDIT"), (False, CREATE)], ids=["inside", "outside"])
def test_scaffold_render_without_a_config_reads_the_working_directory(tmp_path, outside, monkeypatch, inside, expected):
    root, _config, spec = outside
    if inside:
        monkeypatch.chdir(root)
    assert sp.main(["render", "--spec", str(spec), "--out", str(tmp_path / "plan")]) == 0
    assert _ledger_role(tmp_path / "plan") == expected


@pytest.mark.parametrize("command", ["lint-spec", "render", "keys"])
def test_every_caller_lints_at_the_config_root(tmp_path, outside, monkeypatch, capsys, command):
    root, config, spec = outside
    seen, real = [], sp.lint_spec

    def spy(spec, templates_dir=TEMPLATES, project_root=None):
        seen.append(project_root)
        return real(spec, templates_dir, project_root)

    monkeypatch.setattr(sp, "lint_spec", spy)
    main = pb.main if command == "keys" else sp.main
    out = ["--out", str(tmp_path / "plan")] if command == "render" else []
    assert main([command, "--spec", str(spec), *out, "--config", str(config)]) == 0
    assert seen == [root.resolve()]
    # The config's own warning prints once, although the caps and the root both read the file.
    assert capsys.readouterr().err.count("plan_statuses entry") == 1


def test_one_function_derives_the_root_and_a_bad_config_gives_none(tmp_path, outside, capsys):
    root, config, _spec = outside
    assert tss.config_project_root({"_project_root": root}) == root.resolve()
    assert tss.config_project_root({"project_root": str(tmp_path), "_project_root": root}) == tmp_path.resolve()
    assert sp.config_root(str(config)) == root.resolve()
    bad = tmp_path / "bad.yaml"
    bad.write_text("plans_dir: [unterminated\n", encoding="utf-8")
    capsys.readouterr()
    for path in (None, tmp_path / "absent.yaml", bad):
        assert sp.config_root(path) is None
    assert capsys.readouterr() == ("", "")
