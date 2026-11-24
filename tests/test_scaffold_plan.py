"""Tests for scripts/scaffold_plan.py: one known-good and one known-bad case per gate."""

import copy
import json
import re
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import lint_plan_strategy as lps
import scaffold_plan as sp
import token_saver_scan as tss
import token_saver_writeback as tsw

TEMPLATES = sp.DEFAULT_TEMPLATES


def _task(number, name, agent, deps, outputs, rc_path="src/orchard/ledger.py"):
    return {
        "number": number, "name": name, "title": f"Step {number} of the ledger", "agent": agent, "estimate_k": 20 + number,
        "depends_on": deps, "outputs": outputs,
        "required_context": [{"priority": 1, "path": rc_path, "kib": 4.0, "tokens_k": 1.5, "purpose": "the module"}],
    }


def make_spec():
    """Invented sample vocabulary: one sprint, two sessions, two tasks each."""
    return {
        "plan_name": "OrchardLedger", "abbrev": "QZX", "created": "2030-01-15",
        "ordering": "Sprint one only", "resolves": "none",
        "dependencies": [{"dependency": "Ledger schema", "required_for": "first session", "status": "Resolved"}],
        "decisions": [{"id": "D1", "decision": "Keep the ledger flat", "rationale": "One writer"}],
        "sprints": [{
            "number": 1, "name": "LedgerCore", "purpose": "Build the ledger core",
            "sessions": [
                {"number": 1, "name": "ReadPath", "objective": "Read the ledger", "mode": "DELEGATED",
                 "prerequisite": "None (first session)",
                 "tasks": [_task(1, "ParseRows", "Sonnet", [], ["src/orchard/parse.py", "Outputs/QZX-parse.md"]),
                           _task(2, "IndexRows", "Opus", [1], ["src/orchard/index.py"])]},
                {"number": 2, "name": "WritePath", "objective": "Write the ledger", "mode": "DIRECT",
                 "prerequisite": "The read path session",
                 "tasks": [_task(1, "WriteRows", "Sonnet", [], ["src/orchard/write.py"]),
                           _task(2, "VerifyRows", "Sonnet", [1], ["Outputs/QZX-verify.md"])]},
            ],
        }],
    }


@pytest.fixture(scope="module")
def rendered():
    files, _rec = sp.render_all(make_spec(), TEMPLATES)
    return files


def _write(tmp_path, files, name="plan"):
    out = tmp_path / name
    sp.write_tree(files, out)
    return out


def _walk(root):
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


# ---- FILL invariant

def test_fill_invariant_clean_render(rendered):
    for rel, text in rendered.items():
        if rel.endswith(".md"):
            assert sp.unmasked_braces(text) == [], rel


def test_task_cell_starts_with_the_name_the_write_back_reads(rendered):
    """Each Orchestration and Sprint Plan task row names the file's name segment before the title."""
    sprint = next(text for rel, text in rendered.items() if sp.file_kind(rel) == "sprint")
    checked = 0
    for rel in rendered:
        if sp.file_kind(rel) != "task":
            continue
        stem = Path(rel).stem
        number, name = int(stem.split("-")[3]), stem.split("-")[-1]
        orch = next(text for r, text in rendered.items()
                    if sp.file_kind(r) == "orchestration" and Path(r).parent == Path(rel).parent)
        row = f"| {number} | {name}: Step {number} of the ledger |"
        assert row in orch, (rel, row)
        assert row in sprint, (rel, row)
        checked += 1
    assert checked == 4


def test_every_task_file_carries_a_self_row_seeded_at_its_own_size(rendered):
    """The self row names the file by its bare name, takes the next priority, and states the file's bytes."""
    checked = 0
    for rel, text in rendered.items():
        if sp.file_kind(rel) != "task":
            continue
        row = re.search(rf"^\| 2 \| `{re.escape(Path(rel).name)}` \| ([\d,.]+) \| ~([\d.]+)K \| READ \| this task file", text, re.MULTILINE)
        assert row, rel
        size = len(text.encode("utf-8"))
        assert row.group(1) == sp._fmt_kib(size), (rel, size)
        tokens = sp.estimate_tokens(size, "opus" if "-Opus-" in rel else "sonnet", sp.content_class_for(Path("x.md"))[1])
        assert f"~{row.group(2)}K" == sp._fmt_k(tokens), (rel, size)
        # The subtotal's reads term counts the self row beside the spec row (1.5K).
        sub = next(ln for ln in text.split("\n") if ln.startswith("**Context subtotal:**"))
        assert f"~{1.5 + float(row.group(2)):.1f}K" in sub, (rel, sub)
        checked += 1
    assert checked == 4


def test_a_template_without_a_self_row_renders_none(tmp_path):
    shutil.copytree(TEMPLATES, tmp_path / "t")
    path = tmp_path / "t" / "task-file.md"
    text = path.read_text(encoding="utf-8")
    kept = [ln for ln in text.split("\n") if not (ln.startswith("|") and "self row" in ln)]
    assert len(kept) == len(text.split("\n")) - 1  # the control: one example row went
    path.write_text("\n".join(kept), encoding="utf-8")
    files, _ = sp.render_all(make_spec(), tmp_path / "t")
    task = next(t for rel, t in files.items() if sp.file_kind(rel) == "task")
    assert "this task file" not in task


def test_fill_invariant_fires_on_known_bad_line():
    assert sp.unmasked_braces("plain {leaked} text\n") == ["leaked"]
    assert sp.unmasked_braces("ok <!-- FILL: {fine} --> text\n") == []


def test_rendered_task_carries_the_verdict_contract(rendered):
    tasks = {rel: text for rel, text in rendered.items()
             if re.search(r"-S\d{2}-\d{2}-\d{2}-(Sonnet|Opus|Haiku)-", rel)}
    assert len(tasks) == 4
    for rel, text in tasks.items():
        section = text.split("## Verification Commands", 1)[1].split("\n## ", 1)[0]
        for needle in ("[UNCERTAIN]", "count-equality", "never PASS"):
            assert needle in section, (rel, needle)


# ---- lint-spec

def test_lint_good_spec_is_clean():
    assert sp.lint_spec(make_spec(), TEMPLATES) == []


def test_lint_quotes_a_prose_required_context_row():
    spec = make_spec()
    prose = "the ledger parser and its helpers"
    spec["sprints"][0]["sessions"][0]["tasks"][0]["required_context"][0]["path"] = prose
    errors = sp.lint_spec(spec, TEMPLATES)
    assert len(errors) == 1
    assert "prose, not a path" in errors[0]
    assert json.dumps(spec["sprints"][0]["sessions"][0]["tasks"][0]["required_context"][0]) in errors[0]


def test_lint_rejects_missing_field_bad_agent_and_heading_keys():
    spec = make_spec()
    tasks = spec["sprints"][0]["sessions"][1]["tasks"]
    del tasks[0]["title"]
    tasks[1]["agent"] = "Mini"
    spec["extra_sections"] = ["Ledger Notes"]
    spec["optional_sections"] = ["Risk Mitigation"]
    errors = "\n".join(sp.lint_spec(spec, TEMPLATES))
    assert "missing required key 'title'" in errors
    assert "'agent' must be Opus, Sonnet or Haiku" in errors
    assert "unknown key 'extra_sections'" in errors
    assert '"Risk Mitigation" is not an OPTIONAL section' in errors


def test_lint_rejects_a_title_that_repeats_the_task_name():
    spec = make_spec()
    task = spec["sprints"][0]["sessions"][0]["tasks"][0]
    assert task["name"] == "ParseRows"
    task["title"] = "ParseRows: Step 1 of the ledger"
    errors = sp.lint_spec(spec, TEMPLATES)
    assert len(errors) == 1
    assert "'title' repeats the task name" in errors[0]
    for title in ("Parse the ParseRows input", "IndexRows: hand-off"):
        task["title"] = title
        assert sp.lint_spec(spec, TEMPLATES) == [], title


def test_cli_lint_exit_codes(tmp_path):
    good = tmp_path / "good.json"
    good.write_text(json.dumps(make_spec()), encoding="utf-8")
    bad_spec = make_spec()
    bad_spec["sprints"][0]["sessions"][0]["tasks"][1]["required_context"][0]["path"] = "Grep output of the ledger"
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(bad_spec), encoding="utf-8")
    assert sp.main(["lint-spec", "--spec", str(good)]) == 0
    assert sp.main(["lint-spec", "--spec", str(bad)]) == 1


# ---- typed Required Context rows

SPAN_ROW = {"kind": "span", "priority": 2, "path": "docs/orchard-guide.md", "span": "lines 10-40",
            "kib": 2.0, "tokens_k": 0.8, "purpose": "the ledger rules"}
COMMAND_ROW = {"kind": "command", "priority": 3, "command": "Grep 'ledger' over src/orchard", "lines": 12,
               "bytes": "~900", "kib": 0.9, "tokens_k": 0.4, "purpose": "call sites"}
TASK_REL = "Sprint-01-LedgerCore/Session-01-ReadPath/QZX-S01-01-01-Sonnet-ParseRows.md"


def _spec_with_rows(*rows):
    spec = make_spec()
    spec["sprints"][0]["sessions"][0]["tasks"][0]["required_context"].extend(copy.deepcopy(list(rows)))
    return spec


@pytest.mark.parametrize("row", [SPAN_ROW, COMMAND_ROW], ids=["span", "command"])
def test_typed_row_passes_lint_and_renders_in_template_form(row):
    spec = _spec_with_rows(row)
    assert sp.lint_spec(spec, TEMPLATES) == []
    files, _ = sp.render_all(spec, TEMPLATES)
    task = files[TASK_REL]
    assert sp.unmasked_braces(task) == []
    line = next(ln for ln in task.split("\n") if ln.startswith(f"| {row['priority']} |"))
    if row["kind"] == "span":
        assert "`docs/orchard-guide.md` lines 10-40" in line
        assert "— span row" in line
    else:
        assert "`Grep 'ledger' over src/orchard` — 12 lines / ~900 bytes returned" in line
        assert "— command-corpus row" in line


@pytest.mark.parametrize("row,field", [(SPAN_ROW, "span"), (COMMAND_ROW, "bytes")], ids=["span", "command"])
def test_typed_row_missing_a_field_fails_lint_quoted(row, field):
    bad = {k: v for k, v in row.items() if k != field}
    errors = sp.lint_spec(_spec_with_rows(bad), TEMPLATES)
    assert len(errors) == 1
    assert f"missing {field}" in errors[0]
    assert json.dumps(bad) in errors[0]


def test_typed_rows_get_a_resolution_record_and_its_removal_is_detected():
    spec = _spec_with_rows(SPAN_ROW, COMMAND_ROW)
    task = spec["sprints"][0]["sessions"][0]["tasks"][0]
    text = sp.render_all(spec, TEMPLATES)[0][TASK_REL]
    records = [ln for ln in text.split("\n") if not ln.startswith("|") and "2030-01-15: `" in ln]
    assert len(records) == 2, records
    assert any("`docs/orchard-guide.md` lines 10-40" in ln for ln in records)
    assert any("`Grep 'ledger' over src/orchard`" in ln and "12" in ln and "~900" in ln for ln in records)
    assert sp.unmasked_braces(text) == []
    assert sp.resolution_gaps(text, task) == []
    stripped = "\n".join(ln for ln in text.split("\n") if ln not in records)
    assert len(sp.resolution_gaps(stripped, task)) == 2


def test_unknown_row_kind_fails_lint():
    errors = sp.lint_spec(_spec_with_rows(dict(SPAN_ROW, kind="glob")), TEMPLATES)
    assert len(errors) == 1 and "kind must be path, span or command" in errors[0]


# ---- the derived Role column

PIPE_COMMAND_ROW = dict(COMMAND_ROW, priority=4, command="Grep 'ledger|index' over src/orchard")
CREATE_CELL = "CREATE (plan-time estimate)"
SESSION_REL = "Sprint-01-LedgerCore/Session-01-ReadPath"


def _path_row(priority, path):
    return {"priority": priority, "path": path, "kib": 4.0, "tokens_k": 1.5, "purpose": "a file"}


def _project(tmp_path):
    root = tmp_path / "project"
    (root / "src/orchard").mkdir(parents=True)
    (root / "src/orchard/ledger.py").write_text("ledger = {}\n" * 40, encoding="utf-8")
    (root / "docs").mkdir()
    (root / "docs/orchard-guide.md").write_text("A ledger rule.\n" * 60, encoding="utf-8")
    return root


def _context_rows(text):
    """(header cells, {File cell: row cells}) of the Required Context table, every row at the header's width."""
    section = text.split("## Required Context", 1)[1].split("\n**Context subtotal:**", 1)[0]
    table = [ln for ln in section.split("\n") if ln.startswith("|")]
    header = [c.strip() for c in sp.split_row_cells(table[0])]
    rows = [tsw._cells(ln, len(header)) for ln in table[1:]]
    assert {len(r) for r in rows} == {len(header)}, rows
    return header, {r[1].strip(): r for r in rows[1:]}


def _roles(spec, root):
    header, rows = _context_rows(sp.render_all(spec, TEMPLATES, project_root=root)[0][TASK_REL])
    at = header.index("Role")
    return {name: cells[at].strip() for name, cells in rows.items()}


def _write_back(root, text):
    task = root / "plans/QZX" / TASK_REL
    task.parent.mkdir(parents=True)
    task.write_text(text, encoding="utf-8", newline="\n")
    report = tsw.write_estimates([task], root / "plans/QZX", root)
    # The session folder holds no Orchestration, so only the task file's own entries count.
    report["unreadable"] = [u for u in report["unreadable"] if u["file"] == str(task)]
    return task.read_text(encoding="utf-8"), report


def test_every_required_context_row_has_the_header_cell_count(tmp_path):
    spec = _spec_with_rows(SPAN_ROW, COMMAND_ROW, PIPE_COMMAND_ROW)
    header, rows = _context_rows(sp.render_all(spec, TEMPLATES, project_root=tmp_path)[0][TASK_REL])
    assert header == ["Priority", "File", "KiB", "~Tokens", "Role", "Purpose"]
    assert len(rows) == 5  # path, span, two commands, self
    # The template's own separator and five example rows hold the header's width too.
    example = [ln for ln in sp.extract_body(TEMPLATES / "task-file.md").split("\n## Required Context", 1)[1].split("\n")
               if ln.startswith("|")][:7]
    assert [len(sp.split_row_cells(ln)) for ln in example] == [6] * 7


def test_role_reads_from_outputs_and_the_disk(tmp_path):
    root = _project(tmp_path)
    absent = "src/orchard/parse.py"
    full_report = f"plans/QZX/{SESSION_REL}/Outputs/QZX-parse.md"
    spec = _spec_with_rows(SPAN_ROW, COMMAND_ROW, _path_row(5, absent), _path_row(6, "src/other.py"),
                           _path_row(7, "Outputs/QZX-parse.md"), _path_row(8, "Outputs/QZX-peer.md"),
                           _path_row(9, full_report), _path_row(10, "src/orchard/"), _path_row(11, "src/made/"))
    task = _t0(spec)
    task["outputs"] = [absent, "Outputs/QZX-parse.md"]
    span = "`docs/orchard-guide.md` lines 10-40"
    command = "`Grep 'ledger' over src/orchard` — 12 lines / ~900 bytes returned"
    self_cell = f"`{Path(TASK_REL).name}`"
    expected = {"`src/orchard/ledger.py`": "READ", span: "READ", command: "READ", f"`{absent}`": CREATE_CELL,
                "`src/other.py`": "READ", "`Outputs/QZX-parse.md`": CREATE_CELL, "`Outputs/QZX-peer.md`": "READ",
                f"`{full_report}`": CREATE_CELL, "`src/orchard/`": "READ", "`src/made/`": "READ", self_cell: "READ"}
    assert _roles(spec, root) == expected
    # Windows and `./` spellings, an existing and an absent directory, a file below one, a span of an output.
    task["outputs"] = [".\\src\\orchard\\ledger.py", "docs/orchard-guide.md", "./src/orchard", ".\\src\\made"]
    expected.update({"`src/orchard/ledger.py`": "EDIT", span: "EDIT", "`src/orchard/`": "EDIT",
                     "`src/made/`": CREATE_CELL, f"`{absent}`": CREATE_CELL, "`Outputs/QZX-parse.md`": "READ",
                     f"`{full_report}`": "READ"})
    assert _roles(spec, root) == expected
    # The file's own name in `outputs` is the one case where the self row is not READ.
    task["outputs"] = [f"plans/QZX/{TASK_REL}"]
    assert _roles(spec, root)[self_cell] == CREATE_CELL


def test_a_session_output_is_one_file_in_either_spelling(tmp_path):
    root = _project(tmp_path)
    short, full = "Outputs/QZX-parse.md", f"plans/QZX/{SESSION_REL}/Outputs/QZX-parse.md"
    for output, path in ((short, full), (full, short)):
        spec = _spec_with_rows(_path_row(5, path), _path_row(6, "Outputs/QZX-peer.md"))
        _t0(spec)["outputs"] = [output]
        roles = _roles(spec, root)
        assert (roles[f"`{path}`"], roles["`Outputs/QZX-peer.md`"]) == (CREATE_CELL, "READ"), output


@pytest.mark.parametrize("output", ["src/orchard/", "src/orchard", "./src/orchard", ".\\src\\orchard\\",
                                    "{project_root}/src/orchard/"])
def test_a_file_below_an_output_folder_takes_its_role_from_its_own_existence(tmp_path, output):
    root = _project(tmp_path)
    present = ("src/orchard/deep/rows.py", "src/orchard2/ledger.py", "docs/src/orchard/ledger.py")
    for rel in present:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text("rows = []\n", encoding="utf-8")
    expected = {"src/orchard/ledger.py": "EDIT", "src/orchard/deep/rows.py": "EDIT", "src/orchard/": "EDIT",
                "src/orchard/new.py": CREATE_CELL, "src/orchard/made/deep/new.py": CREATE_CELL,
                "src/orchard2/ledger.py": "READ", "src/orchard2/new.py": "READ",
                "docs/src/orchard/ledger.py": "READ", "src/": "READ"}
    # The spec's own row names the first path.
    spec = _spec_with_rows(*(_path_row(i, p) for i, p in enumerate(list(expected)[1:], 3)))
    _t0(spec)["outputs"] = [output]
    roles = _roles(spec, root)
    assert {p: roles[f"`{p}`"] for p in expected} == expected


FULL_OUTPUTS = f"plans/QZX/{SESSION_REL}/Outputs"


@pytest.mark.parametrize("output,path,expected", [
    ("src/made/", "src/made/a.py", "CREATE"),
    ("src/made", "src/made/a.py", "CREATE"),
    ("src/made", "src/made2/a.py", "READ"),
    ("src/orchard/ledger", "src/orchard/ledger.py", "READ"),
    ("src/orchard", "src/orchard/ledger.py (helpers)", "EDIT"),
    ("src/orchard", "src/orchard/new.py (helpers)", "CREATE"),
    ("Outputs/", "Outputs/QZX-parse.md", "CREATE"),
    ("Outputs", f"{FULL_OUTPUTS}/QZX-parse.md", "CREATE"),
    (FULL_OUTPUTS, "Outputs/QZX-parse.md", "CREATE"),
    ("Outputs/rows/", f"{FULL_OUTPUTS}/rows/QZX-parse.md", "CREATE"),
    ("Outputs/rows/", "Outputs/rows2/QZX-parse.md", "READ"),
    (f"plans/QZX/{SESSION_REL}/", "Outputs/QZX-parse.md", "CREATE"),
    (f"plans/QZX/{SESSION_REL}/", f"{FULL_OUTPUTS}/QZX-parse.md", "CREATE"),
    ("plans/ABC/Sprint-01-LedgerCore", "Outputs/QZX-parse.md", "READ"),
    ("src/orchard", "src/orchard/ledger.py:10 (helpers)", "EDIT"),
    ("src/orchard/ledger.py", "src/orchard/ledger.py (helpers)", "EDIT"),
    ("src/orchard/ledger.py", "src/orchard/ledger.py:10-20", "EDIT"),
    ("src/orchard/new.py", "src/orchard/new.py:10 (helpers)", "CREATE"),
    ("docs/orchard-guide.md", "docs/orchard-guide.md (old)", "READ"),  # a file of that name exists
    ("(helpers)", "(helpers)", "CREATE"),
    ("app/(shop)/", "app/page.tsx", "READ"),
    ("app/(shop)/ (new)", "app/page.tsx", "READ"),
    ("app/(shop)/", "app/(shop)/page.tsx", "CREATE"),
    ("app/:10", "app/page.tsx", "READ"),
    ("src/orchard/ledger.py(2)", "src/orchard/ledger.py", "READ"),
])
def test_a_folder_match_starts_at_a_path_component_boundary(tmp_path, output, path, expected):
    sprint, root = make_spec()["sprints"][0], _project(tmp_path)
    (root / "docs/orchard-guide.md (old)").write_text("An old rule.\n", encoding="utf-8")
    assert sp.role_for(path, {"outputs": [output]}, sprint, sprint["sessions"][0], root) == expected


@pytest.mark.parametrize("output,path,expected", [
    *((f"{name}{tail}", name, role)
      for name, role in (("src/orchard/ledger.py", "EDIT"), ("src/orchard/new.py", "CREATE"))
      for tail in (" (new)", ":10", ":10 (new)", " (new) (draft)")),
    ("src/orchard/ (new)", "src/orchard/ledger.py", "EDIT"),
    ("src/orchard (new)", "src/orchard/new.py", "CREATE"),
    ("Outputs/QZX-parse.md (new)", "Outputs/QZX-parse.md", "CREATE"),
    ("./Outputs/ (new)", "Outputs/QZX-parse.md", "CREATE"),
    ("src/orchard/ledger.py (new)", "src/orchard/other.py", "READ"),
    ("src/orchard (new)", "src/orchard2/ledger.py", "READ"),
    ("docs/orchard-guide.md (old)", "docs/orchard-guide.md", "READ"),  # the output is the file of that full name
])
def test_a_qualified_output_matches_a_plain_row(tmp_path, output, path, expected):
    sprint, root = make_spec()["sprints"][0], _project(tmp_path)
    (root / "docs/orchard-guide.md (old)").write_text("An old rule.\n", encoding="utf-8")
    env = SimpleNamespace(task={"outputs": [output]}, sprint=sprint, session=sprint["sessions"][0], project_root=root)
    assert sp.row_role(_path_row(1, path), env).split()[0] == expected
    if output.startswith(path) and expected != "READ":
        # The output text itself reads the same first word.
        assert sp.role_for(output, env.task, env.sprint, env.session, root) == expected


def test_a_qualified_own_file_gives_the_self_row_the_plain_role(tmp_path):
    root, spec = _project(tmp_path), make_spec()
    own = f"plans/QZX/{TASK_REL}"
    self_cell = f"`{Path(TASK_REL).name}`"
    for on_disk, expected in ((False, CREATE_CELL), (True, "EDIT")):
        if on_disk:
            (root / own).parent.mkdir(parents=True)
            (root / own).write_text("# Task\n", encoding="utf-8")
        for output in (own, f"{own} (new)"):
            _t0(spec)["outputs"] = [output]
            assert _roles(spec, root)[self_cell] == expected, output


@pytest.mark.parametrize("output", ["Outputs", "./Outputs/", "Outputs\\x.md", ".\\Outputs\\x.md", "`Outputs/x.md`",
                                    "Outputs (new)", "./Outputs/ (new)", "Outputs:10 (new)"])
def test_a_session_outputs_spelling_is_in_no_write_set(output):
    spec, plain = make_spec(), make_spec()
    _t0(spec)["outputs"] = [output, "docs/Outputs/x.md"]
    _t0(plain)["outputs"] = ["docs/Outputs/x.md"]
    paths = sp.write_paths(spec["sprints"][0])
    assert "docs/Outputs/x.md" in paths
    assert paths == sp.write_paths(plain["sprints"][0])
    rel = sp.sprint_plan_path(spec, spec["sprints"][0])
    got, want = (re.findall(r"^\| `.+ \| QZX-S01-\d\d-\d\d \|.*$", sp.render_all(s, TEMPLATES)[0][rel], re.MULTILINE)
                 for s in (spec, plain))
    assert any("docs/Outputs/x.md" in row for row in got)
    assert got == want


@pytest.mark.parametrize("path,expected", [("Outputs(new)", False), ("Outputs/(x)", True), ("Outputs:10/ (new)", True)])
def test_a_session_outputs_path_drops_whole_qualifiers_only(path, expected):
    assert sp.is_outputs_path(path) is expected


@pytest.mark.parametrize("width", [2, 5], ids=["two", "shipped"])
def test_every_write_set_row_has_the_header_cell_count(tmp_path, width):
    templates = tmp_path / "t"
    shutil.copytree(TEMPLATES, templates)
    path = templates / "sprint-plan.md"
    lines = path.read_text(encoding="utf-8").split("\n")
    head = next(i for i, ln in enumerate(lines) if ln.startswith("| Path | Task |"))
    for i in range(head, head + 4):
        cells = [c.strip() for c in sp.split_row_cells(lines[i])]
        assert len(cells) == 5
        lines[i] = "| " + " | ".join(cells[:width]) + " |"
    path.write_text("\n".join(lines), encoding="utf-8")
    spec = make_spec()
    _t0(spec)["outputs"] = ["src/a|b.py", "src/orchard/", "src/orchard/parse.py (new)", "Outputs/x.md"]
    text = sp.render_all(spec, templates, project_root=_project(tmp_path))[0][
        sp.sprint_plan_path(spec, spec["sprints"][0])]
    section = text.split("\n## Write-Set", 1)[1].split("\n---\n", 1)[0]
    header, _sep, *rows = [sp.split_row_cells(ln) for ln in section.split("\n") if ln.startswith("|")]
    assert [c.strip() for c in header] == ["Path", "Task", "Role", "KiB", "~Tokens"][:width]
    assert len(rows) == 5  # three of the first task, one each of the next two
    assert all(len(r) == width and all(c.strip() for c in r) for r in rows), rows
    assert rows[0][0].strip() == "`src/a|b.py`"


@pytest.mark.parametrize("width", [2, 5], ids=["two", "shipped"])
def test_every_master_write_sets_row_has_the_header_cell_count(tmp_path, width):
    templates = tmp_path / "t"
    shutil.copytree(TEMPLATES, templates)
    path = templates / "master-plan.md"
    lines = path.read_text(encoding="utf-8").split("\n")
    head = next(i for i, ln in enumerate(lines) if ln.startswith("| Sprint | Write-set |"))
    for i in range(head, head + 4):
        cells = [c.strip() for c in sp.split_row_cells(lines[i])]
        assert len(cells) == 5
        lines[i] = "| " + " | ".join(cells[:width]) + " |"
    path.write_text("\n".join(lines), encoding="utf-8")
    spec = _two_sprint_spec()
    _t0(spec)["outputs"] = ["src/a|b.py", "src/orchard/parse.py (new)"]
    for session in spec["sprints"][1]["sessions"]:
        for task in session["tasks"]:
            task["outputs"] = ["Outputs/x.md"]
    text = sp.render_all(spec, templates, project_root=_project(tmp_path))[0]["QZX-Master-Plan.md"]
    section = text.split("\n### Write-Sets", 1)[1].split("\n### ", 1)[0]
    header, _sep, *rows = [[c.strip() for c in sp.split_row_cells(ln)] for ln in section.split("\n")
                           if ln.startswith("|")]
    assert header == ["Sprint", "Write-set", "Count", "KiB", "~Tokens"][:width]
    assert len(rows) == 2
    assert all(len(r) == width and all(r) for r in rows), rows
    assert rows[0][1].startswith("`src/a|b.py`, ")
    assert rows[1] == ["Sprint-02", "none", "0", "0.0", "~0.0K"][:width]


INDEX = "src/orchard/index.py"
OWN_OUTPUT = "Sprint-01-LedgerCore/Session-01-ReadPath/Outputs/QZX-a.md"


@pytest.mark.parametrize("first,second,shared", [
    ([INDEX], [f"{INDEX} (rows)"], [INDEX]),
    ([f"{INDEX}:1-9", "b.py"], ["c.py", f"./{INDEX}"], [f"{INDEX}:1-9"]),
    (["src\\orchard\\index.py"], [INDEX], ["src\\orchard\\index.py"]),
    (["Outputs/QZX-a.md"], [f"plans/QZX/{OWN_OUTPUT}"], ["Outputs/QZX-a.md"]),
    ([INDEX, "Outputs/QZX-a.md"], ["Outputs/QZX-a.md", INDEX], ["Outputs/QZX-a.md", INDEX]),  # plain: as before
    (["none"], ["none"], ["none"]),  # plain: as before
    ([INDEX, f"{INDEX} (rows)"], ["src/orchard/parse.py"], []),  # one task, two spellings
    (["Outputs/QZX-a.md"], [f"plans/QZX/{OWN_OUTPUT.replace('-01-ReadPath', '-02-WritePath')}"], []),
])
def test_two_spellings_in_one_layer_are_not_disjoint(tmp_path, first, second, shared):
    spec = make_spec()
    spec["sprints"][0]["sessions"][0]["tasks"] = [_task(1, "ParseRows", "Sonnet", [], first),
                                                  _task(2, "IndexRows", "Opus", [], second)]
    files = sp.render_all(spec, TEMPLATES, project_root=tmp_path)[0]
    text = next(t for rel, t in files.items() if rel.endswith("S01-01-Orchestration.md"))
    row = next(ln for ln in text.split("\n") if ln.startswith("| L1 | {1, 2} |"))
    cells = [c.strip() for c in row.strip("|").split("|")]
    assert cells[2] == " / ".join(", ".join(f"`{o}`" for o in outs) for outs in (first, second))
    assert cells[3] == (", ".join(f"`{s}`" for s in shared) or "∅")
    assert ("NOT" in cells[4]) == bool(shared)


def test_role_expands_the_root_placeholders(tmp_path):
    root = _project(tmp_path)
    (root / "planwise").mkdir()
    (root / "planwise/notes.md").write_text("A note.\n", encoding="utf-8")
    spec = _spec_with_rows()
    sprint = spec["sprints"][0]
    session = sprint["sessions"][0]

    def role(output, path):
        return sp.role_for(path, {"outputs": [output]}, sprint, session, root)

    for braced, plain, expected in (("{planwise_root}/notes.md", "planwise/notes.md", "EDIT"),
                                    ("{project_root}/src/orchard/ledger.py", "src/orchard/ledger.py", "EDIT"),
                                    ("{planwise_root}/new.md", "planwise/new.md", "CREATE"),
                                    ("{plugin_root}/templates/task-file.md",
                                     (TEMPLATES / "task-file.md").as_posix(), "EDIT"),
                                    ("{plugin_root}/templates/absent.md",
                                     (TEMPLATES / "absent.md").as_posix(), "CREATE")):
        got = [role(a, b) for a in (braced, plain) for b in (braced, plain)]
        assert got == [expected] * 4, braced


@pytest.mark.parametrize("role_at", [None, 2, 4], ids=["five", "moved", "shipped"])
def test_the_role_cell_follows_the_template_header(tmp_path, role_at):
    templates = tmp_path / "t"
    shutil.copytree(TEMPLATES, templates)
    path = templates / "task-file.md"
    lines = path.read_text(encoding="utf-8").split("\n")
    head = next(i for i, ln in enumerate(lines) if ln.startswith("| Priority | File | KiB |"))
    for i in range(head, head + 7):
        cells = [c.strip() for c in sp.split_row_cells(lines[i])]
        role = cells.pop(4)
        if role_at is not None:
            cells.insert(role_at, role)
        lines[i] = "| " + " | ".join(cells) + " |"
    path.write_text("\n".join(lines), encoding="utf-8")
    spec = _spec_with_rows(SPAN_ROW, COMMAND_ROW)
    text = sp.render_all(spec, templates, project_root=_project(tmp_path))[0][TASK_REL]
    table = [ln for ln in text.split("\n## Required Context", 1)[1].split("\n**Context subtotal:**", 1)[0].split("\n")
             if ln.startswith("|")]
    header, _sep, *rows = [[c.strip() for c in sp.split_row_cells(ln)] for ln in table]
    assert len(rows) == 4  # path, span, command, self
    assert {len(r) for r in rows} == {len(header)} == {5 if role_at is None else 6}
    assert [r[header.index("Role")] for r in rows] == ["READ"] * 4 if role_at is not None else "Role" not in header
    assert rows[-1][header.index("Purpose")].startswith("this task file")


def test_write_back_prices_every_row_of_a_rendered_task_and_keeps_role(tmp_path):
    root = _project(tmp_path)
    spec = _spec_with_rows(SPAN_ROW, COMMAND_ROW, PIPE_COMMAND_ROW)
    _t0(spec)["outputs"] = ["src/orchard/ledger.py"]
    text = sp.render_all(spec, TEMPLATES, project_root=root)[0][TASK_REL]
    after, report = _write_back(root, text.replace("<!-- FILL: {O} -->", "2").replace("<!-- FILL: {W} -->", "1"))
    assert (report["errors"], report["unreadable"]) == ([], [])
    assert [r["reason"] for r in report["left"]] == ["command corpus"] * 2  # each keeps its dry-run figure
    header, rows = _context_rows(after)
    ledger = rows["`src/orchard/ledger.py`"]
    assert ledger[header.index("KiB")].strip() == sp._fmt_kib((root / "src/orchard/ledger.py").stat().st_size)
    assert ledger[header.index("Role")].strip() == "EDIT"
    own = rows[f"`{Path(TASK_REL).name}`"]
    assert own[header.index("KiB")].strip() == sp._fmt_kib(len(after.encode("utf-8")))


# Rows copied from a task file the five-column renderer wrote, with the two subtotal fills answered.
OLD_SHAPE_TASK = """# Task: Sonnet-ParseRows

**Task ID:** QZX-S01-01-01
**Agent:** Sonnet
**Estimated Tokens:** ~21K

## Required Context <!-- REQUIRED -->

| Priority | File | KiB | ~Tokens | Purpose |
|----------|------|----:|--------:|---------|
| 1 | `src/orchard/ledger.py` | 4.0 | ~1.5K | the module |
| 2 | `docs/orchard-guide.md` lines 10-40 | 2.0 | ~0.8K | the ledger rules — span row, see the resolution comment below |
| 4 | `QZX-S01-01-01-Sonnet-ParseRows.md` | 28.5 | ~11.2K | this task file — self row, measured by the write-back after the last edit |

**Context subtotal:** ~13.5K (reads — the sum of the ~Tokens column) + ~2K (output) + ~1K (working) = **~21K total**
"""


def test_a_five_column_task_file_still_prices_every_row(tmp_path):
    root = _project(tmp_path)
    after, report = _write_back(root, OLD_SHAPE_TASK)
    assert (report["errors"], report["left"], report["unreadable"]) == ([], [], [])
    header, rows = _context_rows(after)
    assert header == ["Priority", "File", "KiB", "~Tokens", "Purpose"]  # the write-back adds no column
    span_bytes = sum(map(len, (root / "docs/orchard-guide.md").read_bytes().splitlines(keepends=True)[9:40]))
    sizes = {"`src/orchard/ledger.py`": (root / "src/orchard/ledger.py").stat().st_size,
             "`docs/orchard-guide.md` lines 10-40": span_bytes,
             f"`{Path(TASK_REL).name}`": len(after.encode("utf-8"))}
    assert {name: cells[2].strip() for name, cells in rows.items()} == {n: sp._fmt_kib(s) for n, s in sizes.items()}
    parsed = tss.parse_required_context(after)
    assert [r["file_cell"] for r in parsed] == list(sizes)
    plan, task = root / "plans/QZX", root / "plans/QZX" / TASK_REL
    assert all(tsw.price_row(r["file_cell"], task, plan, root, "sonnet")["priced"] for r in parsed)


# ---- check-headings

def test_check_headings_fresh_render_has_no_stray(tmp_path, rendered):
    out = _write(tmp_path, rendered)
    results = sp.check_headings([out], TEMPLATES)
    assert len([r for r in results if r["kind"]]) == 10
    assert [r for r in results if r["stray"]] == []
    assert sp.main(["check-headings", str(out)]) == 0


def test_check_headings_flags_a_hand_added_h2(tmp_path, rendered):
    out = _write(tmp_path, rendered)
    target = out / "QZX-Master-Plan.md"
    target.write_bytes(target.read_bytes().replace(b"## Dependencies", b"## Ledger Notes\n\nx\n\n## Dependencies"))
    results = sp.check_headings([target], TEMPLATES)
    assert results[0]["stray"] == ["## Ledger Notes"]
    assert sp.main(["check-headings", str(out)]) == 1


def test_check_headings_plan_specific_h3_accepted_and_later_h2_stray(tmp_path):
    spec = make_spec()
    spec["optional_sections"] = ["Plan-Specific Sections"]
    files, _rec = sp.render_all(spec, TEMPLATES)
    text = files["QZX-Master-Plan.md"]
    assert "\n## Plan-Specific Sections" in text
    ok = text + "\n### Ledger Notes\n\nkept\n"
    assert sp.check_text(ok, *sp.template_heading_sets(TEMPLATES)["master"])[1] == []
    bad = ok + "\n## References\n"
    assert sp.check_text(bad, *sp.template_heading_sets(TEMPLATES)["master"])[1] == ["## References"]


def _scaffolding_master_text():
    """A Master Plan body filled from the scaffolding template's own fenced body."""
    return sp.read_lf(TEMPLATES / "scaffolding-master-plan.md").split("```markdown\n", 1)[1].split("\n```\n", 1)[0] + "\n"


def test_check_headings_grades_a_scaffolding_master_against_its_own_template(tmp_path, capsys):
    target = tmp_path / "QZX-Master-Plan.md"
    target.write_text(_scaffolding_master_text(), encoding="utf-8", newline="\n")
    results = sp.check_headings([target], TEMPLATES)
    assert (results[0]["kind"], results[0]["stray"]) == ("scaffolding-master", [])
    assert results[0]["h2"] == 12
    assert sp.main(["check-headings", str(target)]) == 0
    out = capsys.readouterr().out
    assert "kind=scaffolding-master" in out and "stray=0" in out and "stray_h2=0 files=1" in out


def test_check_headings_keeps_grading_a_standard_master_as_master(tmp_path, rendered):
    out = _write(tmp_path, rendered)
    target = out / "QZX-Master-Plan.md"
    target.write_bytes(target.read_bytes().replace(
        b"## Dependencies", b"## Sprint-to-Part Mapping\n\nx\n\n## Dependencies"))
    results = sp.check_headings([target], TEMPLATES)
    assert (results[0]["kind"], results[0]["stray"]) == ("master", ["## Sprint-to-Part Mapping"])


def test_check_headings_flags_an_h2_after_the_scaffolding_catch_all(tmp_path):
    target = tmp_path / "QZX-Master-Plan.md"
    target.write_text(_scaffolding_master_text() + "\n## Unknown Notes\n\nx\n", encoding="utf-8", newline="\n")
    results = sp.check_headings([target], TEMPLATES)
    assert (results[0]["kind"], results[0]["stray"]) == ("scaffolding-master", ["## Unknown Notes"])


def test_check_headings_ignores_h2_inside_a_fence():
    patterns, catch = sp.template_heading_sets(TEMPLATES)["task"]
    text = "## Objective\n\n```markdown\n## Not A Section\n```\n\n## Notes for Agent\n"
    assert sp.check_text(text, patterns, catch) == (2, [])


# ---- check-scope-line

SCOPE_CLAUSE = "Execute ONLY"
ORCH_DELEGATED = "Sprint-01-LedgerCore/Session-01-ReadPath/QZX-S01-01-Orchestration.md"
ORCH_DIRECT = "Sprint-01-LedgerCore/Session-02-WritePath/QZX-S01-02-Orchestration.md"


def test_check_scope_line_fresh_render_passes_and_skips_direct(tmp_path, rendered):
    out = _write(tmp_path, rendered)
    results = sp.check_scope_lines([out])
    assert [(Path(r["path"]).name, r["count"]) for r in results] == [("QZX-S01-01-Orchestration.md", 1)]
    assert sp.main(["check-scope-line", str(out)]) == 0


def test_check_scope_line_flags_a_removed_clause(tmp_path, rendered):
    out = _write(tmp_path, rendered)
    target = out / ORCH_DELEGATED
    target.write_bytes(target.read_bytes().replace(SCOPE_CLAUSE.encode(), b"Run"))
    assert sp.check_scope_lines([target])[0]["count"] == 0
    assert sp.main(["check-scope-line", str(out)]) == 1


def test_check_scope_line_flags_a_duplicated_clause(tmp_path, rendered):
    out = _write(tmp_path, rendered)
    target = out / ORCH_DELEGATED
    target.write_bytes(target.read_bytes() + b"\n" + SCOPE_CLAUSE.encode() + b" QZX-S01-01-01.\n")
    assert sp.check_scope_lines([target])[0]["count"] == 2
    assert sp.main(["check-scope-line", str(out)]) == 1


def test_check_scope_line_skips_a_direct_orchestration_and_reports_a_missing_path(tmp_path, rendered):
    out = _write(tmp_path, rendered)
    direct = out / ORCH_DIRECT
    direct.write_bytes(direct.read_bytes().replace(SCOPE_CLAUSE.encode(), b"Run"))
    assert sp.check_scope_lines([direct]) == []
    assert sp.main(["check-scope-line", str(direct)]) == 0
    assert sp.main(["check-scope-line", str(tmp_path / "no-such-folder")]) == 2


# ---- orchestration Required Context by mode

REFERENCE_DOCS = ("session-planning-protocol.md", "session-context-budget.md", "session-plan-requirements.md")


def _required_context_files(text):
    section = text.split("## Required Context Files", 1)[1].split("\n---", 1)[0]
    return re.findall(r"^\| \d \| `([^`]+)` \|", section, flags=re.MULTILINE)


def test_delegated_orchestration_lints_clean_and_lists_plan_files_only(tmp_path, rendered):
    out = _write(tmp_path, rendered)
    assert lps.main([str(out / ORCH_DELEGATED)]) == 0
    text = (out / ORCH_DELEGATED).read_text(encoding="utf-8")
    assert _required_context_files(text) == ["QZX-Master-Plan.md", "QZX-S01-01-Recovery.md"]
    assert not any(name in text.split("## Execution Strategy", 1)[0] for name in REFERENCE_DOCS)


def test_direct_orchestration_keeps_the_reference_doc_rows_and_lints_clean(tmp_path, rendered):
    out = _write(tmp_path, rendered)
    assert lps.main([str(out / ORCH_DIRECT)]) == 0
    text = (out / ORCH_DIRECT).read_text(encoding="utf-8")
    assert _required_context_files(text) == [*REFERENCE_DOCS, "QZX-Master-Plan.md", "QZX-S01-02-Recovery.md"]


def test_delegated_known_bad_unfiltered_table_fails_the_linter(tmp_path, rendered):
    out = _write(tmp_path, rendered)
    target = out / ORCH_DELEGATED
    direct = (out / ORCH_DIRECT).read_text(encoding="utf-8")
    table = direct.split("## Required Context Files", 1)[1].split("\n---", 1)[0]
    text = target.read_text(encoding="utf-8")
    old = text.split("## Required Context Files", 1)[1].split("\n---", 1)[0]
    target.write_text(text.replace(old, table), encoding="utf-8", newline="\n")
    assert lps.main([str(target)]) == 1


# ---- file set

def test_rendered_paths_equal_the_spec_derived_set(tmp_path, rendered):
    out = _write(tmp_path, rendered)
    expected = sorted(sp.plan_paths(make_spec()))
    assert _walk(out) == expected
    assert len(expected) == 12  # master + sprint + 2 sessions x (orchestration, recovery, 2 tasks, .gitkeep)
    task = next(out.rglob("QZX-S01-01-01-Sonnet-ParseRows.md"))
    task.rename(task.with_name("QZX-S01-01-01-Sonnet-ParseRowz.md"))
    assert _walk(out) != expected


# ---- line endings, post-fence sections, OPTIONAL sections

def test_crlf_template_input_gives_lf_output(tmp_path):
    lf_dir, crlf_dir = tmp_path / "lf", tmp_path / "crlf"
    lf_dir.mkdir()
    crlf_dir.mkdir()
    for name in sp.TEMPLATE_FILES.values():
        text = (TEMPLATES / name).read_bytes().replace(b"\r\n", b"\n")
        (lf_dir / name).write_bytes(text)
        (crlf_dir / name).write_bytes(text.replace(b"\n", b"\r\n"))
    lf_files, _ = sp.render_all(make_spec(), lf_dir)
    crlf_files, _ = sp.render_all(make_spec(), crlf_dir)
    assert crlf_files == lf_files
    assert all("\r" not in t for t in crlf_files.values())


def test_recovery_post_fence_sections_are_not_rendered(rendered):
    recovery = next(t for rel, t in rendered.items() if rel.endswith("-Recovery.md"))
    post_fence = [ln for ln in sp.read_lf(TEMPLATES / "recovery.md").split("\n")[
        max(i for i, ln in enumerate(sp.read_lf(TEMPLATES / "recovery.md").split("\n")) if ln.startswith("```")):]
        if ln.startswith("## ")]
    assert post_fence, "the recovery template carries no H2 after its closing fence"
    for heading in post_fence:
        assert heading not in recovery


def test_optional_section_omitted_unless_opted_in():
    spec = make_spec()
    plain, _ = sp.render_all(spec, TEMPLATES)
    assert "## Out of Scope" not in plain["QZX-Master-Plan.md"]
    opted = copy.deepcopy(spec)
    opted["optional_sections"] = ["Out of Scope"]
    files, _ = sp.render_all(opted, TEMPLATES)
    assert "## Out of Scope" in files["QZX-Master-Plan.md"]
    assert sp.unmasked_braces(files["QZX-Master-Plan.md"]) == []


META_H3S = ["Source Material", "Expected Consolidated Context Parts", "Hypotheses", "User-Action Gates"]
GATED_SESSION = "Sprint-01-LedgerCore/Session-01-ReadPath/QZX-S01-01-"
OTHER_SESSION = "Sprint-01-LedgerCore/Session-02-WritePath/QZX-S01-02-"


def test_meta_plan_sections_render_only_when_opted_in():
    plain, _ = sp.render_all(make_spec(), TEMPLATES)
    assert "## Discovery Inputs" not in plain["QZX-Master-Plan.md"]
    # The heading line, not the phrase: the Recovery Change Log note names the section in prose.
    assert "\n## User-Action Gate" not in plain[GATED_SESSION + "Orchestration.md"]
    assert "\n## User-Action Gate" not in plain[GATED_SESSION + "Recovery.md"]

    opted = make_spec()
    opted["optional_sections"] = ["Discovery Inputs"]
    opted["sprints"][0]["sessions"][0]["optional_sections"] = ["User-Action Gate"]
    files, _ = sp.render_all(opted, TEMPLATES)

    master = files["QZX-Master-Plan.md"]
    assert master.count("\n## Discovery Inputs") == 1
    for heading in META_H3S:
        assert master.count(f"\n### {heading}\n") == 1, heading
    assert sp.check_text(master, *sp.template_heading_sets(TEMPLATES)["master"])[1] == []

    for kind in ("Orchestration", "Recovery"):
        gated = files[GATED_SESSION + kind + ".md"]
        assert gated.count("\n## User-Action Gate") == 1, kind
        assert "\n## User-Action Gate" not in files[OTHER_SESSION + kind + ".md"], kind
        assert sp.check_text(gated, *sp.template_heading_sets(TEMPLATES)[kind.lower()])[1] == [], kind


def test_schema_pin_fence_parity_is_bounded(rendered):
    depth = 0
    for line in ("```", "**Schema Pin**", "```sql", "DDL", "```", "Live as of", "```"):
        depth = sp.fence_step(line, depth)
    assert depth == 0
    task = rendered["Sprint-01-LedgerCore/Session-01-ReadPath/QZX-S01-01-01-Sonnet-ParseRows.md"]
    assert "Live as of: {YYYY-MM-DD}" in task
    assert "> [!constraint] No `~?` Placeholders in Token Estimates" in task


# ---- refusal

def test_render_refuses_a_non_empty_out(tmp_path):
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(make_spec()), encoding="utf-8")
    out = tmp_path / "out"
    out.mkdir()
    (out / "keep.md").write_text("x", encoding="utf-8")
    assert sp.main(["render", "--spec", str(spec_path), "--out", str(out)]) == 2
    assert _walk(out) == ["keep.md"]
    fresh = tmp_path / "fresh"
    assert sp.main(["render", "--spec", str(spec_path), "--out", str(fresh)]) == 0
    assert _walk(fresh) == sorted(sp.plan_paths(make_spec()))
    shutil.rmtree(fresh)


# A spec that json.loads cannot turn into a value: an integer past the 4,300-digit conversion limit
# (ValueError), nesting deeper than the recursion limit (RecursionError), and plain malformed text.
UNPARSEABLE_SPECS = {"huge-int": "1" * 5000, "deep-nesting": "[" * 100000, "bad": "{bad"}


@pytest.mark.parametrize("payload", UNPARSEABLE_SPECS.values(), ids=UNPARSEABLE_SPECS.keys())
def test_render_and_lint_spec_refuse_an_unparseable_spec(tmp_path, capsys, payload):
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(payload, encoding="utf-8")
    out = tmp_path / "out"
    assert sp.main(["render", "--spec", str(spec_path), "--out", str(out)]) == 2
    assert "REFUSED: cannot read spec" in capsys.readouterr().out
    assert not out.exists()
    assert sp.main(["lint-spec", "--spec", str(spec_path)]) == 2
    assert "ERROR: cannot read spec" in capsys.readouterr().out


# ---- review fixes: one known-good and one known-bad case per correctness finding

def _bare_env():
    return SimpleNamespace(tmpl="t", rec=sp.Rec(), vals={}, spec={}, item={})


def test_comments_stripped_on_plain_lines_only():
    body = ("## Notes\n\nplain <!-- gone one -->\n<!-- gone two -->\n> <!-- callout kept -->\n"
            "```text\n<!-- fence kept -->\n```\n")
    text = sp.render_doc(body, _bare_env(), [])
    assert "gone" not in text
    assert "> <!-- callout kept -->" in text
    assert "<!-- fence kept -->" in text


def test_task_file_keeps_the_callout_exemplar_comment(rendered):
    task = rendered[TASK_REL]
    assert "> <!-- netted to ~34K by the targeted-read discipline" in task
    assert "Delete rows 3 and 4 above" not in task  # a plain-line comment is still stripped


def _two_sprint_spec():
    spec = make_spec()
    second = copy.deepcopy(spec["sprints"][0])
    second.update(number=2, name="LedgerExtras")
    spec["sprints"].append(second)
    return spec


def _t0(spec):
    return spec["sprints"][0]["sessions"][0]["tasks"][0]


TYPE_CASES = {
    "outputs_empty": (lambda s: _t0(s).update(outputs=[]), "'outputs' must be a non-empty list"),
    "outputs_string": (lambda s: _t0(s).update(outputs="src/a.py"), "'outputs' must be a non-empty list"),
    "kib_string": (lambda s: _t0(s)["required_context"][0].update(kib="4"), "'kib' must be a number"),
    "tokens_k_string": (lambda s: _t0(s)["required_context"][0].update(tokens_k="1.5"),
                        "'tokens_k' must be a number"),
    "sprint_number_string": (lambda s: s["sprints"][0].update(number="1"), "'number' must be an integer"),
    "task_number_bool": (lambda s: _t0(s).update(number=True), "'number' must be an integer"),
    "depends_on_bool": (lambda s: s["sprints"][0]["sessions"][0]["tasks"][1].update(depends_on=[True]),
                        "'depends_on' must be a list of task numbers"),
    "pair_unhashable": (lambda s: s.update(parallel_pairs=[[[1], 1]]), "is not a pair of two different"),
    "pair_self": (lambda s: s.update(parallel_pairs=[[1, 1]]), "is not a pair of two different"),
}


def test_typed_fields_known_good_pair_and_types_lint_clean():
    spec = _two_sprint_spec()
    spec["parallel_pairs"] = [[1, 2]]
    assert sp.lint_spec(spec, TEMPLATES) == []
    files, _ = sp.render_all(spec, TEMPLATES)
    assert "| Sprint-01 ∥ Sprint-02 |" in files["QZX-Master-Plan.md"]


@pytest.mark.parametrize("case", sorted(TYPE_CASES))
def test_typed_field_errors_are_lint_lines_and_render_refuses(tmp_path, capsys, case):
    mutate, expected = TYPE_CASES[case]
    spec = make_spec()
    mutate(spec)
    errors = sp.lint_spec(spec, TEMPLATES)
    assert any(expected in e for e in errors), errors
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    assert sp.main(["render", "--spec", str(spec_path), "--out", str(tmp_path / "out")]) == 2
    assert not (tmp_path / "out").exists()
    assert any(ln.startswith("LINT: ") and expected in ln for ln in capsys.readouterr().out.splitlines())


DUPLICATE_CASES = {
    "sprint": (lambda s: s["sprints"][1].update(number=1), "duplicate sprint number 1"),
    "session": (lambda s: s["sprints"][0]["sessions"][1].update(number=1), "duplicate session number 1"),
    "task": (lambda s: s["sprints"][0]["sessions"][0]["tasks"][1].update(number=1), "duplicate task number 1"),
}


@pytest.mark.parametrize("case", sorted(DUPLICATE_CASES))
def test_duplicate_numbers_fail_lint(case):
    mutate, expected = DUPLICATE_CASES[case]
    spec = _two_sprint_spec()
    assert sp.lint_spec(spec, TEMPLATES) == []
    mutate(spec)
    assert any(expected in e for e in sp.lint_spec(spec, TEMPLATES))


def test_render_all_refuses_to_overwrite_a_path_it_produced():
    spec = make_spec()
    assert len(sp.render_all(spec, TEMPLATES)[0]) == 12
    spec["sprints"][0]["sessions"][1].update(number=1, name="ReadPath")
    with pytest.raises(AssertionError, match="already produced"):
        sp.render_all(spec, TEMPLATES)


@pytest.mark.parametrize("path", ["Makefile", "Dockerfile", "src/orchard/", "src/output_writer.py",
                                  "docs/output-format.md"])
def test_one_word_paths_are_not_prose(path):
    spec = make_spec()
    _t0(spec)["required_context"][0]["path"] = path
    assert sp.lint_spec(spec, TEMPLATES) == []


@pytest.mark.parametrize("path", ["the ledger parser and its helpers", "Grep 'ledger' over src/orchard"])
def test_multi_word_prose_paths_still_fail_lint(path):
    spec = make_spec()
    _t0(spec)["required_context"][0]["path"] = path
    errors = sp.lint_spec(spec, TEMPLATES)
    assert len(errors) == 1 and "prose, not a path" in errors[0]


def test_template_h2_inside_a_closed_fence_does_not_desync():
    patterns, catch = sp.template_heading_sets(TEMPLATES)["task"]
    pasted = "## Objective\n\n```markdown\n## Objective\n```\n\n## Ledger Notes\n"
    assert sp.check_text(pasted, patterns, catch) == (2, ["## Ledger Notes"])


def test_template_h2_inside_a_stuck_fence_still_resyncs():
    patterns, catch = sp.template_heading_sets(TEMPLATES)["task"]
    stuck = "## Objective\n\n```\nnever closed\n\n## Notes for Agent\n"
    assert sp.check_text(stuck, patterns, catch) == (2, [])


OUTPUT_LINE = "**Output:** {path where deliverable should be saved, e.g., Outputs/{Abbrev}-{description}.md}"


def test_handler_rewrites_a_wrapped_field_line_whole(tmp_path, rendered):
    expected = "**Output:** `src/orchard/parse.py`, and `Outputs/QZX-parse.md`"
    assert expected in rendered[TASK_REL].split("\n")
    for name in sp.TEMPLATE_FILES.values():
        text = sp.read_lf(TEMPLATES / name)
        if name == "task-file.md":
            assert OUTPUT_LINE in text
            text = text.replace(OUTPUT_LINE, OUTPUT_LINE.replace("saved, e.g.", "saved,\ne.g."))
        (tmp_path / name).write_bytes(text.encode("utf-8"))
    task = sp.render_all(make_spec(), tmp_path)[0][TASK_REL]
    assert expected in task.split("\n")
    assert "e.g., Outputs/" not in task


def test_render_reports_a_residual_failure_in_one_line(tmp_path, capsys, monkeypatch):
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(make_spec()), encoding="utf-8")

    def boom(*_args):
        raise ValueError("first\nsecond")

    monkeypatch.setattr(sp, "render_all", boom)
    assert sp.main(["render", "--spec", str(spec_path), "--out", str(tmp_path / "out")]) == 2
    out = capsys.readouterr().out.splitlines()
    assert out == [("REFUSED: the render failed on a lint-clean spec (ValueError: first second). "
                    "Fix: correct the spec; lint-spec did not catch this case.")]
