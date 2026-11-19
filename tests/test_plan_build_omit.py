"""Tests for the `omit_sections` key and the `apply` step of scripts/plan_build.py.

Shared helpers live in `tests/test_plan_build.py`.
"""

import sys
from pathlib import Path

import pytest

sys.dont_write_bytecode = True
TESTS = Path(__file__).resolve().parent
SCRIPTS = TESTS.parent / "plugins" / "planwise" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(TESTS))

import plan_build as pb
import scaffold_plan as sp
from test_plan_build import (
    DOC_PATTERN,
    FILLED_RE,
    OBJECTIVE,
    ORCH_DOC,
    PLAN_RE,
    SCHEMA_PIN,
    TASK_DOC,
    TEMPLATES,
    TWICE,
    Build,
    _build_owned_spec,
    _write_bodies,
    _write_spec,
    add_keys,
    bodies_set,
    deviations,
    index_of,
    make_spec,
    run_script,
    spec_with_omits,
    summary,
    under,
)


@pytest.fixture(scope="module")
def rendered():
    return sp.render_all(make_spec(), TEMPLATES)[0]


@pytest.fixture(scope="module")
def index(rendered):
    return pb.doc_index(rendered, TEMPLATES)


# ---- omission

def test_omit_names_come_from_the_templates():
    names = pb.omittable_names(TEMPLATES)
    for name in (SCHEMA_PIN, "USED-Helper Enumeration", "Verification Commands", "Field Mapping",
                 "Comparison-Task Coverage Row", "Change-Surface Census", "Cross-Sprint Prerequisite Grep Gate",
                 "References Moved That May Now Be False", "Verbatim-Copy Line-Count Range"):
        assert name in names["task"]
    assert "Context Boundary" in names["orchestration"]
    for name in ("Execution Steps", "Per-File-Type Commands", "Plan-Specific Sections"):
        assert name not in names["task"]
    for name in ("Dispatch Layers", "Session Start Census", "Status Block delivery (REQUIRED)"):
        assert name not in names["orchestration"]


def test_omit_known_good_records_the_line_and_passes_the_deviation_gate(tmp_path, capsys):
    spec = spec_with_omits(task_omits=[SCHEMA_PIN])
    build = Build(tmp_path, capsys, bodies_set(index_of(tmp_path, spec)), spec)
    code, out = build.run()
    assert code == 0, out
    text = build.task_file().read_text(encoding="utf-8")
    assert "<!-- OMITTED: Schema Pin (spec omit_sections) -->" in text.split("\n")
    assert "### Schema Pin" not in text
    assert "### Schema Pin" in build.task_file(number=2).read_text(encoding="utf-8")
    assert deviations(build.out) == []


def test_omit_every_allowed_name_keeps_the_deviation_gate_silent(tmp_path, capsys):
    names = pb.omittable_names(TEMPLATES)
    spec = spec_with_omits(task_omits=names["task"], session_omits=names["orchestration"])
    build = Build(tmp_path, capsys, bodies_set(index_of(tmp_path, spec)), spec)
    code, out = build.run()
    assert code == 0, out
    text = build.task_file().read_text(encoding="utf-8")
    assert text.count("<!-- OMITTED: ") == len(names["task"])
    assert deviations(build.out) == []


def test_omit_control_the_deviation_gate_sees_a_built_tree(tmp_path, capsys, index):
    build = Build(tmp_path, capsys, bodies_set(index))
    assert build.run()[0] == 0
    assert deviations(build.out) == []
    target = build.task_file()
    target.write_text(target.read_text(encoding="utf-8").replace("## Objective", "## Goal"), encoding="utf-8")
    found = deviations(build.out)
    assert len(found) == 1
    assert found[0].startswith("CLASS_A ") and found[0].endswith('missing "## Objective"')


def test_omit_known_bad_rejects_a_required_heading_and_writes_nothing(tmp_path, capsys, index):
    build = Build(tmp_path, capsys, bodies_set(index), spec_with_omits(task_omits=["Execution Steps"]))
    code, out = build.run()
    assert code == 2
    assert 'task S01-01-01: omit_sections names "Execution Steps"' in out
    assert not build.out.exists()
    assert not build.manifest.exists()


def test_omit_lint_and_keys_refuse_the_same_name(tmp_path, capsys, index):
    spec_path = _write_spec(tmp_path, spec_with_omits(task_omits=["Execution Steps"]))
    assert pb.main(["keys", "--spec", str(spec_path)]) == 2
    bodies = _write_bodies(tmp_path, bodies_set(index))
    assert pb.main(["lint", "--spec", str(spec_path), "--bodies-dir", str(bodies)]) == 2
    assert capsys.readouterr().out.count('names "Execution Steps"') == 2


def test_omit_a_task_cannot_name_an_orchestration_heading(tmp_path, capsys):
    assert pb.main(["keys", "--spec", str(_write_spec(tmp_path, spec_with_omits(task_omits=["Context Boundary"])))]) == 2
    assert 'names "Context Boundary"' in capsys.readouterr().out


def test_omit_rejects_a_value_that_is_no_list(tmp_path, capsys):
    spec = make_spec()
    spec["sprints"][0]["sessions"][0]["omit_sections"] = SCHEMA_PIN
    assert pb.main(["keys", "--spec", str(_write_spec(tmp_path, spec))]) == 2
    assert "session S01-01: omit_sections must be a list" in capsys.readouterr().out


def test_omit_a_session_name_reaches_its_orchestration_and_its_tasks(tmp_path):
    spec = spec_with_omits(session_omits=["Context Boundary", SCHEMA_PIN])
    idx = index_of(tmp_path, spec)
    assert "### Context Boundary" not in idx[ORCH_DOC]["headings"]
    for doc in (TASK_DOC, "S01-01-02"):
        assert "### Schema Pin" not in idx[doc]["headings"]
    assert "### Schema Pin" in idx["S01-02-01"]["headings"]


def test_omit_h2_takes_its_h3_sections_and_its_separator(tmp_path):
    idx = index_of(tmp_path, spec_with_omits(task_omits=["Verification Commands"]))
    heads = idx[TASK_DOC]["headings"]
    assert "## Verification Commands" not in heads
    assert "### Per-File-Type Commands" not in heads
    assert "## Success Criteria" in heads
    text = "# T\n\n## Keep\n\nx\n\n---\n\n## Gone\n\ny\n\n### Child\n\nz\n\n---\n\n## Next\n"
    assert pb.omit_section(text, "Gone", DOC_PATTERN) == (
        "# T\n\n## Keep\n\nx\n\n---\n\n<!-- OMITTED: Gone (spec omit_sections) -->\n\n## Next\n")


def test_omit_h3_keeps_the_separator_of_its_parent():
    text = "## Keep\n\nx\n\n### Gone (Required when asked)\n\ny\n\n---\n\n## Next\n"
    assert pb.omit_section(text, "Gone", DOC_PATTERN) == (
        "## Keep\n\nx\n\n<!-- OMITTED: Gone (spec omit_sections) -->\n\n---\n\n## Next\n")


def test_omit_a_heading_inside_a_fence_ends_no_span():
    text = "### Gone\n\n```text\n### Fenced\n```\n\n### Next\n"
    assert pb.omit_section(text, "Gone", DOC_PATTERN) == "\n<!-- OMITTED: Gone (spec omit_sections) -->\n\n### Next\n"


@pytest.mark.parametrize("name,after", [
    (SCHEMA_PIN, "**In DELEGATED sessions:**"),
    ("Cross-Sprint Prerequisite Grep Gate", "**Interface Consumption:**"),
], ids=["schema-pin", "cross-sprint"])
def test_omit_keeps_the_first_kept_line_and_what_follows(tmp_path, capsys, name, after):
    spec = spec_with_omits(task_omits=[name])
    build = Build(tmp_path, capsys, bodies_set(index_of(tmp_path, spec)), spec)
    assert build.run()[0] == 0
    lines = build.task_file().read_text(encoding="utf-8").split("\n")
    site = lines.index(f"<!-- OMITTED: {name} (spec omit_sections) -->")
    assert lines[site + 2].startswith(pb.FIRST_KEPT_LINES[name])
    assert any(after in ln for ln in lines[site + 2:])
    assert not any(ln.startswith(f"### {name}") for ln in lines)


def test_omit_cuts_the_text_above_the_first_kept_line(tmp_path):
    spec = spec_with_omits(task_omits=[SCHEMA_PIN, "Cross-Sprint Prerequisite Grep Gate"])
    path = _write_spec(tmp_path, spec)
    text = next(t for rel, t in pb.render_core(str(path), TEMPLATES)[1].items() if pb.doc_id(rel) == TASK_DOC)
    assert "Missing Schema Pin for SQL-emitting tasks" not in text
    assert "Authoring rules:" not in text


@pytest.mark.parametrize("name", sorted(pb.FIRST_KEPT_LINES))
def test_omit_first_kept_line_is_still_in_its_template_section(name):
    assert name in pb.omittable_names(TEMPLATES)["task"]
    lines = sp.extract_body(TEMPLATES / sp.TEMPLATE_FILES["task"]).split("\n")
    levels = pb.heading_levels(lines, DOC_PATTERN)
    k = next(j for j, level in levels.items() if level > 1 and pb.heading_name(lines[j]) == name)
    section = lines[k + 1:pb.span_end(levels, k, len(lines))]
    assert any(ln.startswith(pb.FIRST_KEPT_LINES[name]) for ln in section), name


def test_omit_a_section_with_no_stop_line_runs_to_its_heading_bound():
    text = "### Schema Pin\n\nold\n\n---\n\n## Next\n"
    assert pb.omit_section(text, SCHEMA_PIN, DOC_PATTERN) == (
        "\n<!-- OMITTED: Schema Pin (spec omit_sections) -->\n\n---\n\n## Next\n")


@pytest.mark.parametrize("level,quoted", [("plan", "plan level:"), ("sprint", "sprint 01 level:")])
def test_omit_at_sprint_or_plan_level_is_a_lint_error(tmp_path, capsys, index, level, quoted):
    spec = make_spec()
    (spec if level == "plan" else spec["sprints"][0])["omit_sections"] = [SCHEMA_PIN]
    build = Build(tmp_path, capsys, bodies_set(index), spec)
    code, out = build.run()
    assert code == 2
    assert f"LINT: {quoted} omit_sections belongs on a session or a task" in out.splitlines()
    assert not build.out.exists()


def test_omit_stripper_removes_the_key_at_session_and_task_level():
    core = pb.core_spec(_build_owned_spec())
    session = core["sprints"][0]["sessions"][0]
    assert "omit_sections" not in session
    assert "omit_sections" not in session["tasks"][0]


def test_omit_a_doc_without_the_heading_stays_as_it_is():
    assert pb.omit_section("## Keep\n", "Gone", DOC_PATTERN) == "## Keep\n"


def test_omit_a_body_for_a_cut_marker_is_a_lint_error(tmp_path, capsys, index):
    marker = next(m[0] for m in index[TASK_DOC]["markers"] if m[1] == "## Verification Commands")
    spec = spec_with_omits(task_omits=["Verification Commands"])
    bodies = add_keys(bodies_set(index_of(tmp_path, spec)), TASK_DOC, f"<!-- fill: {marker} -->\n\nx\n")
    code, out = Build(tmp_path, capsys, bodies, spec).run()
    assert code == 2
    assert "the marker occurs nowhere in this doc" in out


# ---- apply

def test_apply_known_good_leaves_no_marker(tmp_path, capsys, index):
    build = Build(tmp_path, capsys, bodies_set(index))
    code, out = build.run()
    assert code == 0, out
    assert FILLED_RE.search(out).group(1) == "0"
    assert "surviving_placeholders=0" in out
    texts = [p.read_text(encoding="utf-8") for p in build.out.rglob("*.md")]
    assert len(texts) == len(index)
    assert not any("<!-- FILL: " in t for t in texts)
    assert f"Body for {TASK_DOC}." in build.task_file().read_text(encoding="utf-8")


def test_apply_known_bad_counts_the_marker_and_exits_1(tmp_path, capsys, index):
    build = Build(tmp_path, capsys, bodies_set(index, skip={(TASK_DOC, OBJECTIVE)}))
    code, out = build.run()
    assert code == 1
    assert FILLED_RE.search(out).group(1) == "1"
    assert f"<!-- FILL: {{{OBJECTIVE}}} -->" in build.task_file().read_text(encoding="utf-8")
    assert build.manifest.exists()


def test_apply_fill_remaining_equals_the_lint_keys_missing(tmp_path, capsys, index):
    skip = {(TASK_DOC, OBJECTIVE), (TASK_DOC, TWICE), ("S01-02-01", OBJECTIVE), ("MASTER", index["MASTER"]["markers"][0][0])}
    bodies = add_keys(bodies_set(index, skip=skip), TASK_DOC,
                      f"<!-- section: ## Objective -->\n\nGoal.\n\n<!-- fill: {TWICE} [2] -->\n\nSecond.\n")
    build = Build(tmp_path, capsys, bodies)
    lint_code = pb.main(["lint", "--spec", str(build.spec), "--bodies-dir", str(build.bodies)])
    lint_out = capsys.readouterr().out
    assert lint_code == 1
    missing = int(PLAN_RE.search(lint_out).group(1)) + sum(m for m, _e in summary(lint_out).values())
    code, out = build.run()
    assert code == 1
    assert int(FILLED_RE.search(out).group(1)) == missing == 3
    on_disk = sum(p.read_text(encoding="utf-8").count("<!-- FILL: ") for p in build.out.rglob("*.md"))
    assert on_disk == missing


def test_apply_a_bare_fill_takes_every_occurrence_and_an_index_takes_one():
    text = "<!-- FILL: {a} --> <!-- FILL: {a} -->\n<!-- FILL: {a} -->\n"
    body = {"fills": {("a", None): "bare", ("a", 2): "second"}, "sections": {}}
    assert pb.apply_doc(text, body, DOC_PATTERN) == ("bare second\nbare\n", 0)


def test_apply_an_index_alone_leaves_the_other_occurrence():
    text = "<!-- FILL: {a} -->\n<!-- FILL: {a} -->\n"
    body = {"fills": {("a", 2): "second"}, "sections": {}}
    assert pb.apply_doc(text, body, DOC_PATTERN) == ("<!-- FILL: {a} -->\nsecond\n", 1)


def test_apply_a_section_replaces_its_span_and_keeps_the_separator():
    text = "## One\n\n<!-- FILL: {a} -->\n\n### Sub\n\n<!-- FILL: {b} -->\n\n---\n\n## Two\n\n<!-- FILL: {a} -->\n"
    body = {"fills": {("a", 2): "later"}, "sections": {"## One": "Text."}}
    assert pb.apply_doc(text, body, DOC_PATTERN) == ("## One\n\nText.\n\n---\n\n## Two\n\nlater\n", 0)


@pytest.mark.parametrize("name,cut,after,skip_marker,left", [
    (SCHEMA_PIN, "Missing Schema Pin for SQL-emitting tasks", "**In DELEGATED sessions:**", None, 0),
    ("Cross-Sprint Prerequisite Grep Gate", "Authoring rules:", "**Interface Consumption:**", "field_name", 1),
], ids=["schema-pin", "cross-sprint"])
def test_apply_a_section_body_stops_at_the_first_kept_line(tmp_path, capsys, index, name, cut, after, skip_marker, left):
    heading = next(h for h in index[TASK_DOC]["headings"] if h.startswith(f"### {name}"))
    skip = under(index, TASK_DOC, heading) | ({(TASK_DOC, skip_marker)} if skip_marker else set())
    assert not skip_marker or any(m[0] == skip_marker and m[2] is None for m in index[TASK_DOC]["markers"])
    build = Build(tmp_path, capsys, add_keys(bodies_set(index, skip=skip), TASK_DOC,
                                             f"<!-- section: {heading} -->\n\nSection text.\n"))
    assert pb.main(["lint", "--spec", str(build.spec), "--bodies-dir", str(build.bodies)]) == (1 if left else 0)
    lint_out = capsys.readouterr().out
    code, out = build.run()
    assert code == (1 if left else 0), out
    assert int(FILLED_RE.search(out).group(1)) == summary(lint_out)["S01-01"][0] == left
    text = build.task_file().read_text(encoding="utf-8")
    lines = text.split("\n")
    site = lines.index("Section text.")
    assert lines[site + 2].startswith(pb.FIRST_KEPT_LINES[name])
    assert any(after in ln for ln in lines[site + 2:])
    assert cut not in text
    assert text.count("<!-- FILL: ") == left


def test_apply_a_section_at_the_end_of_a_doc():
    assert pb.apply_doc("## One\n\nold\n", {"fills": {}, "sections": {"## One": "New."}}, DOC_PATTERN) == (
        "## One\n\nNew.\n", 0)


def test_apply_an_empty_body_counts_as_no_body():
    text = "## One\n\n<!-- FILL: {a} -->\n"
    body = {"fills": {("a", None): ""}, "sections": {"## One": ""}}
    assert pb.apply_doc(text, body, DOC_PATTERN) == (text, 1)


def test_apply_keeps_marker_text_inside_a_body():
    text = "<!-- FILL: {a} -->\n<!-- FILL: {b} -->\n"
    body = {"fills": {("a", None): "<!-- FILL: {b} -->", ("b", None): "B"}, "sections": {}}
    assert pb.apply_doc(text, body, DOC_PATTERN) == ("<!-- FILL: {b} -->\nB\n", 0)


def test_apply_a_body_with_braces_is_no_surviving_placeholder(tmp_path, capsys, index):
    keys = "<!-- section: ## Notes for Agent -->\n\nUse {value} here.\n"
    bodies = bodies_set(index, skip=under(index, TASK_DOC, "## Notes for Agent"))
    code, out = Build(tmp_path, capsys, add_keys(bodies, TASK_DOC, keys)).run()
    assert code == 0, out
    assert "surviving_placeholders=0" in out


def test_apply_a_bodies_lint_error_writes_nothing(tmp_path, capsys, index):
    bodies = add_keys(bodies_set(index), TASK_DOC, "<!-- fill: Ledger goal -->\n\nGoal.\n")
    build = Build(tmp_path, capsys, bodies)
    code, out = build.run()
    assert code == 2
    assert f"LINT: doc={TASK_DOC} key=fill: Ledger goal: the marker occurs nowhere in this doc" in out
    assert not build.out.exists()


def test_apply_date_reaches_the_tree(tmp_path, capsys, index):
    build = Build(tmp_path, capsys, bodies_set(index))
    code, out = build.run("--date", "2031-02-03")
    assert code == 0, out
    assert any("2031-02-03" in p.read_text(encoding="utf-8") for p in build.out.rglob("*.md"))


@pytest.mark.parametrize("flag,value,reason", [
    ("--date", "soon", "is not YYYY-MM-DD"),
    ("--config", "absent.yaml", "is not a file"),
    ("--bodies-dir", "absent", "is not a folder"),
], ids=["date", "config", "bodies"])
def test_apply_refuses_a_bad_argument(tmp_path, capsys, index, flag, value, reason):
    build = Build(tmp_path, capsys, bodies_set(index))
    code = pb.main([*build.argv(), flag, str(tmp_path / value) if flag != "--date" else value])
    assert code == 2
    assert reason in capsys.readouterr().out
    assert not build.out.exists()


@pytest.mark.parametrize("extra", [(), ("--force",)], ids=["guarded", "force"])
def test_apply_refuses_an_out_path_that_is_a_file(tmp_path, capsys, index, extra):
    build = Build(tmp_path, capsys, bodies_set(index))
    build.out.write_text("mine\n", encoding="utf-8")
    code, out = build.run(*extra)
    assert code == 2
    assert out.splitlines() == [f"REFUSED: {build.out} is not a folder. Fix: pass a folder for --out."]
    assert build.out.read_text(encoding="utf-8") == "mine\n"
    assert not build.manifest.exists()


def test_apply_build_as_a_process(tmp_path, capsys, index):
    build = Build(tmp_path, capsys, bodies_set(index))
    result = run_script(*build.argv())
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.startswith("built ")
