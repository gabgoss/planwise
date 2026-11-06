"""Tests for scripts/plan_build.py: one known-good and one known-bad case per rule.

Marker names and headings come from a real render of the templates, never from invented rows.
"""

import copy
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

sys.dont_write_bytecode = True
SCRIPTS = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import plan_build as pb
import scaffold_deviations as sd
import scaffold_plan as sp

TEMPLATES = sp.DEFAULT_TEMPLATES
TASK_DOC = "S01-01-01"
ORCH_DOC = "S01-01-ORCH"
OBJECTIVE = "Clear, specific goal for this task - what must be accomplished"
TWICE = "1-line purpose"  # occurs twice in a rendered task file
ESTIMATE_BODIES = {"O": "4", "W": "6"}  # the write-back reads these two markers as numbers
SUMMARY_RE = re.compile(r"^session=(\S+) keys_missing=(\d+) errors=(\d+)$", re.MULTILINE)
PLAN_RE = re.compile(r"^plan missing=(\d+) errors=(\d+)$", re.MULTILINE)


def _task(number, name, agent, deps, outputs):
    return {
        "number": number, "name": name, "title": f"{name} work", "agent": agent, "estimate_k": 20 + number,
        "depends_on": deps, "outputs": outputs,
        "required_context": [{"priority": 1, "path": "src/orchard/ledger.py", "kib": 4.0, "tokens_k": 1.5,
                              "purpose": "the module"}],
    }


def make_spec():
    """Invented sample vocabulary: one sprint, two sessions, two tasks each."""
    return {
        "plan_name": "OrchardLedger", "abbrev": "QZX", "created": "2030-01-15",
        "ordering": "Sprint one only", "resolves": "none",
        "dependencies": [{"dependency": "Ledger schema", "required_for": "first session", "status": "Resolved"}],
        "decisions": [{"id": "Q1", "decision": "Keep the ledger flat", "rationale": "One writer"}],
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


def _build_owned_spec():
    spec = make_spec()
    spec["meta"] = {"owner": "ledger team"}
    session = spec["sprints"][0]["sessions"][0]
    session["omit_sections"] = ["Context Boundary"]
    session["meta"] = {"note": "first"}
    task = session["tasks"][0]
    task.update(estimate_k="auto", output_k=4, working_k=6, omit_sections=["Schema Pin"])
    return spec


@pytest.fixture(scope="module")
def rendered():
    return sp.render_all(make_spec(), TEMPLATES)[0]


@pytest.fixture(scope="module")
def index(rendered):
    return pb.doc_index(rendered, TEMPLATES)


def bodies_set(index, skip=()):
    """{file name: text} with one body per distinct marker of every document, minus `skip` (doc, name) pairs."""
    out = {}
    for doc, info in index.items():
        group = pb.session_of(doc)
        name = "QZX-bodies-plan.md" if group == pb.PLAN_GROUP else f"QZX-bodies-{group}.md"
        lines = [f"<!-- doc: {doc} -->", ""]
        for marker in dict.fromkeys(m[0] for m in info["markers"]):
            if (doc, marker) not in skip:
                lines += [f"<!-- fill: {marker} -->", "", ESTIMATE_BODIES.get(marker, f"Body for {doc}."), ""]
        out[name] = out.get(name, "") + "\n".join(lines) + "\n"
    return out


def under(index, doc, heading):
    """The (doc, marker) pairs a section body at `heading` replaces, for the `skip` of `bodies_set`."""
    return {(doc, m[0]) for m in index[doc]["markers"] if heading in m[1:]}


def add_keys(bodies, doc, text):
    """A copy of `bodies` with `text` placed first in the document block of `doc`."""
    opener = f"<!-- doc: {doc} -->\n"
    out = {name: body.replace(opener, f"{opener}\n{text}\n") for name, body in bodies.items()}
    assert out != bodies, doc
    return out


def _write_spec(tmp_path, spec=None):
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(spec or make_spec()), encoding="utf-8")
    return path


def _write_bodies(tmp_path, bodies):
    folder = tmp_path / "bodies"
    folder.mkdir()
    for name, text in bodies.items():
        (folder / name).write_bytes(text.encode("utf-8"))
    return folder


def run_lint(tmp_path, capsys, bodies, *extra):
    """Run the lint command in process. Return (exit code, stdout)."""
    args = ["lint", "--spec", str(_write_spec(tmp_path)), "--bodies-dir", str(_write_bodies(tmp_path, bodies))]
    code = pb.main([*args, *extra])
    return code, capsys.readouterr().out


def run_script(*args):
    """Run plan_build.py as a process, the way a session runs it."""
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    return subprocess.run([sys.executable, "-B", str(SCRIPTS / "plan_build.py"), *args], capture_output=True,
                          encoding="utf-8", env=env, check=False, timeout=60)


def summary(out):
    return {g: (int(missing), int(errors)) for g, missing, errors in SUMMARY_RE.findall(out)}


# ---- core spec

def test_core_spec_strips_build_keys_and_passes_lint():
    spec = _build_owned_spec()
    before = copy.deepcopy(spec)
    assert sp.lint_spec(spec, TEMPLATES) != []
    core = pb.core_spec(spec)
    assert sp.lint_spec(core, TEMPLATES) == []
    assert core["sprints"][0]["sessions"][0]["tasks"][0]["estimate_k"] == pb.AUTO_ESTIMATE_VALUE
    assert spec == before
    assert sp.render_all(core, TEMPLATES)[0]


def test_core_spec_keeps_every_other_bad_value_for_the_lint():
    spec = _build_owned_spec()
    spec["extra_sections"] = ["Ledger Notes"]
    spec["sprints"][0]["sessions"][0]["tasks"][1]["estimate_k"] = "soon"
    errors = "\n".join(sp.lint_spec(pb.core_spec(spec), TEMPLATES))
    assert "unknown key 'extra_sections'" in errors
    assert "'estimate_k' must be a number" in errors


# ---- doc ids

def test_doc_ids_name_every_rendered_document(rendered, index):
    assert list(index) == ["MASTER", "S01", "S01-01-ORCH", "S01-01-RECOVERY", "S01-01-01", "S01-01-02",
                           "S01-02-ORCH", "S01-02-RECOVERY", "S01-02-01", "S01-02-02"]
    assert len(index) == sum(1 for rel in rendered if rel.endswith(".md"))


def test_doc_id_skips_a_path_that_is_no_plan_document():
    assert pb.doc_id("QZX-notes.md") is None
    assert pb.doc_id("Outputs/.gitkeep") is None


def _task_named(name):
    spec = make_spec()
    spec["sprints"][0]["sessions"][0]["tasks"][1]["name"] = name
    return spec


@pytest.mark.parametrize("name,kind", [("Recovery", "RECOVERY"), ("Orchestration", "ORCH")])
def test_doc_id_a_task_named_like_a_session_doc_is_refused(tmp_path, name, kind):
    result = run_script("keys", "--spec", str(_write_spec(tmp_path, _task_named(name))))
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stdout.startswith(f"REFUSED: doc id S01-01-{kind} belongs to two files: ")
    assert f"QZX-S01-01-{name}.md" in result.stdout and f"QZX-S01-01-02-Opus-{name}.md" in result.stdout


def test_doc_id_a_task_name_that_only_holds_the_word_is_accepted(tmp_path):
    result = run_script("keys", "--spec", str(_write_spec(tmp_path, _task_named("RecoveryRows"))))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "doc S01-01-02 " in result.stdout


def test_doc_id_collision_refuses_lint_and_build_too(tmp_path, capsys, index):
    build = Build(tmp_path, capsys, bodies_set(index), _task_named("Recovery"))
    code, out = build.run()
    assert code == 2 and "belongs to two files" in out, out
    assert not build.out.exists()
    assert pb.main(["lint", "--spec", str(build.spec), "--bodies-dir", str(build.bodies)]) == 2


# ---- keys

def test_keys_doc_count(tmp_path):
    spec_path = _write_spec(tmp_path)
    result = run_script("keys", "--spec", str(spec_path))
    assert result.returncode == 0, result.stdout + result.stderr
    files, _rec = sp.render_all(make_spec(), TEMPLATES)
    doc_ids = [d for d in map(pb.doc_id, files) if d]
    lines = result.stdout.splitlines()
    doc_lines = [ln for ln in lines if ln.startswith("doc ")]
    assert len(doc_lines) == len(doc_ids) == 10
    assert [ln.split()[1] for ln in doc_lines] == doc_ids
    fill_markers = sum(t.count("<!-- FILL: ") for t in files.values())
    assert sum(int(ln.rsplit("markers=", 1)[1]) for ln in doc_lines) == fill_markers
    assert sum(int(ln.rsplit("count=", 1)[1]) for ln in lines if ln.startswith("  marker ")) == fill_markers
    assert lines[-1] == f"fill_markers={fill_markers} docs={len(doc_ids)}"


def test_keys_prints_first_occurrence_order_and_headings(tmp_path):
    out = run_script("keys", "--spec", str(_write_spec(tmp_path))).stdout.splitlines()
    block = out[out.index(next(ln for ln in out if ln.startswith(f"doc {TASK_DOC} "))) + 1:]
    assert block[0] == f"  marker {OBJECTIVE} count=1"
    assert f"  marker {TWICE} count=2" in block
    heads = next(ln for ln in block if ln.startswith("  headings: "))
    assert heads.startswith("  headings: ## Objective | ## Required Context | ### Comparison-Task Coverage Row (")
    assert "### Schema Pin |" in heads
    assert "<!--" not in heads


def test_keys_omits_an_h2_inside_a_fence(index):
    heads = index[ORCH_DOC]["headings"]
    assert "## Spawn-Prompt Skeleton" in heads
    assert "### Context Boundary" in heads
    assert "## HARD CONSTRAINTS (non-negotiable)" not in heads
    assert "## SCOPE BOUNDARY" not in heads


def test_keys_h2_list_equals_the_heading_gate_count(rendered, index):
    sets = sp.template_heading_sets(TEMPLATES)
    for rel, text in rendered.items():
        doc = pb.doc_id(rel)
        if doc:
            count, _strays = sp.check_text(text, *sets[sp.file_kind(rel)])
            assert sum(1 for h in index[doc]["headings"] if h.startswith("## ")) == count, rel


def test_keys_accepts_a_spec_with_build_keys(tmp_path):
    result = run_script("keys", "--spec", str(_write_spec(tmp_path, _build_owned_spec())))
    assert result.returncode == 0, result.stdout


def test_keys_refuses_a_spec_with_a_lint_error(tmp_path):
    spec = make_spec()
    spec["sprints"][0]["sessions"][0]["tasks"][0]["agent"] = "Mini"
    result = run_script("keys", "--spec", str(_write_spec(tmp_path, spec)))
    assert result.returncode == 2
    assert "'agent' must be Opus, Sonnet or Haiku" in result.stdout
    assert not any(ln.startswith("doc ") for ln in result.stdout.splitlines())


def test_keys_refuses_an_unreadable_spec(tmp_path):
    assert run_script("keys", "--spec", str(tmp_path / "absent.json")).returncode == 2


# ---- lint summary line

def test_lint_summary_known_good_prints_keys_missing_zero(tmp_path, capsys, index):
    code, out = run_lint(tmp_path, capsys, bodies_set(index))
    assert code == 0, out
    assert "session=S01-01 keys_missing=0 errors=0" in out.splitlines()
    assert summary(out) == {"S01-01": (0, 0), "S01-02": (0, 0)}
    assert out.splitlines()[0] == "plan missing=0 errors=0"
    assert out.count("keys_missing=0") == 2  # one per session: the plan line adds nothing to this count
    assert out.count("session=") == 2


def test_lint_summary_known_bad_prints_keys_missing_one(tmp_path, capsys, index):
    code, out = run_lint(tmp_path, capsys, bodies_set(index, skip={(TASK_DOC, OBJECTIVE)}))
    assert code == 1
    assert "session=S01-01 keys_missing=1 errors=0" in out.splitlines()
    assert summary(out)["S01-02"] == (0, 0)


def test_lint_counts_a_plan_document_marker_in_the_plan_group(tmp_path, capsys, index):
    marker = index["MASTER"]["markers"][0][0]
    code, out = run_lint(tmp_path, capsys, bodies_set(index, skip={("MASTER", marker)}))
    assert code == 1
    assert out.splitlines()[0] == "plan missing=1 errors=0"
    assert summary(out) == {"S01-01": (0, 0), "S01-02": (0, 0)}


def test_lint_missing_counts_occurrences_not_names(tmp_path, capsys, index):
    code, out = run_lint(tmp_path, capsys, bodies_set(index, skip={(TASK_DOC, TWICE)}))
    assert code == 1
    assert summary(out)["S01-01"] == (2, 0)


def test_lint_empty_folder_reports_every_marker_missing(tmp_path, capsys, index):
    code, out = run_lint(tmp_path, capsys, {})
    assert code == 1
    plan_missing = int(PLAN_RE.search(out).group(1))
    assert plan_missing + sum(missing for missing, _errors in summary(out).values()) == sum(
        len(info["markers"]) for info in index.values())


def test_lint_an_empty_body_counts_as_missing(tmp_path, capsys, index):
    bodies = add_keys(bodies_set(index, skip={(TASK_DOC, OBJECTIVE)}), TASK_DOC, f"<!-- fill: {OBJECTIVE} -->\n")
    code, out = run_lint(tmp_path, capsys, bodies)
    assert code == 1
    assert summary(out)["S01-01"] == (1, 0)


def test_lint_a_whitespace_only_body_counts_as_missing(tmp_path, capsys, index):
    bodies = add_keys(bodies_set(index, skip={(TASK_DOC, OBJECTIVE)}), TASK_DOC, f"<!-- fill: {OBJECTIVE} -->\n   \n\t\n")
    code, out = run_lint(tmp_path, capsys, bodies)
    assert code == 1, out
    assert summary(out)["S01-01"] == (1, 0)


def test_parse_stores_a_whitespace_only_body_as_no_body():
    docs, errors = pb.parse_bodies(f"<!-- doc: {TASK_DOC} -->\n<!-- section: ## One -->\n  \n<!-- fill: a -->\n \t\n")
    assert errors == []
    assert docs[TASK_DOC]["sections"] == {"## One": ""}
    assert docs[TASK_DOC]["fills"] == {("a", None): ""}


# ---- rule: unknown doc

def test_lint_known_doc_passes(index):
    docs, errors = pb.parse_bodies(f"<!-- doc: {ORCH_DOC} -->\n")
    assert errors == []
    assert pb.lint_bodies(index, docs)[0] == []


def test_lint_unknown_doc_names_doc_and_exits_2(tmp_path, capsys, index):
    bodies = bodies_set(index)
    bodies["QZX-bodies-S01-01.md"] += "<!-- doc: S01-01-09 -->\n"
    code, out = run_lint(tmp_path, capsys, bodies)
    assert code == 2
    assert "LINT: doc=S01-01-09 key=doc: the doc is not in the rendered tree" in out.splitlines()
    assert summary(out)["S01-01"] == (0, 1)


# ---- rule: unknown fill name

def test_lint_fill_name_folds_whitespace_on_both_sides(tmp_path, capsys, index):
    folded = OBJECTIVE.replace("specific goal", "specific   goal")
    bodies = add_keys(bodies_set(index, skip={(TASK_DOC, OBJECTIVE)}), TASK_DOC, f"<!-- fill:   {folded}  -->\n\nGoal.\n")
    code, out = run_lint(tmp_path, capsys, bodies)
    assert code == 0, out


def test_lint_unknown_fill_names_key_and_doc(tmp_path, capsys, index):
    code, out = run_lint(tmp_path, capsys, add_keys(bodies_set(index), TASK_DOC, "<!-- fill: Ledger goal -->\n\nGoal.\n"))
    assert code == 2
    assert f"LINT: doc={TASK_DOC} key=fill: Ledger goal: the marker occurs nowhere in this doc" in out.splitlines()


def test_lint_a_marker_of_another_doc_is_unknown_here(tmp_path, capsys, index):
    other = "session-base value"
    assert any(m[0] == other for m in index[ORCH_DOC]["markers"])
    code, out = run_lint(tmp_path, capsys, add_keys(bodies_set(index), TASK_DOC, f"<!-- fill: {other} -->\n\nx\n"))
    assert code == 2
    assert f"doc={TASK_DOC} key=fill: {other}:" in out


# ---- rule: fill occurrence index

def test_lint_indexed_bodies_cover_each_occurrence(tmp_path, capsys, index):
    keys = f"<!-- fill: {TWICE} [1] -->\n\nFirst.\n\n<!-- fill: {TWICE} [2] -->\n\nSecond.\n"
    code, out = run_lint(tmp_path, capsys, add_keys(bodies_set(index, skip={(TASK_DOC, TWICE)}), TASK_DOC, keys))
    assert code == 0, out


def test_lint_one_indexed_body_leaves_the_other_occurrence_missing(tmp_path, capsys, index):
    bodies = add_keys(bodies_set(index, skip={(TASK_DOC, TWICE)}), TASK_DOC, f"<!-- fill: {TWICE} [2] -->\n\nSecond.\n")
    code, out = run_lint(tmp_path, capsys, bodies)
    assert code == 1
    assert summary(out)["S01-01"] == (1, 0)


@pytest.mark.parametrize("k", [0, 3])
def test_lint_index_past_the_count_names_key_and_doc(tmp_path, capsys, index, k):
    code, out = run_lint(tmp_path, capsys, add_keys(bodies_set(index), TASK_DOC, f"<!-- fill: {TWICE} [{k}] -->\n\nx\n"))
    assert code == 2
    assert f"LINT: doc={TASK_DOC} key=fill: {TWICE} [{k}]: the marker occurs 2 time(s) in this doc" in out.splitlines()


def test_parse_splits_the_index_from_the_name():
    docs, errors = pb.parse_bodies(f"<!-- doc: {TASK_DOC} -->\n<!-- fill: Step 1 [2] -->\n\nBody one.\n\nBody two.\n")
    assert errors == []
    assert docs[TASK_DOC]["fills"] == {("Step 1", 2): "Body one.\n\nBody two."}


# ---- rule: section heading

@pytest.mark.parametrize("doc,heading", [
    (TASK_DOC, "## Objective"),
    (TASK_DOC, "### Schema Pin"),
    (TASK_DOC, "### Field Mapping (Required for MERGE/upsert tasks)"),
    (ORCH_DOC, "### Context Boundary"),
    (ORCH_DOC, "## Dispatch Layers"),
], ids=["h2", "conditional-h3", "required-tail-h3", "orchestration-conditional", "orchestration-required-tail"])
def test_lint_every_template_heading_form_is_a_section_key(tmp_path, capsys, index, doc, heading):
    assert heading in index[doc]["headings"]
    bodies = add_keys(bodies_set(index, skip=under(index, doc, heading)), doc, f"<!-- section: {heading} -->\n\nText.\n")
    code, out = run_lint(tmp_path, capsys, bodies)
    assert code == 0, out


def test_lint_absent_section_names_key_and_doc(tmp_path, capsys, index):
    code, out = run_lint(tmp_path, capsys, add_keys(bodies_set(index), TASK_DOC, "<!-- section: ## Ledger Notes -->\n\nx\n"))
    assert code == 2
    assert f"LINT: doc={TASK_DOC} key=section: ## Ledger Notes: the heading is absent from this doc" in out.splitlines()


def test_lint_a_section_body_covers_the_markers_under_its_heading(tmp_path, capsys, index):
    bodies = add_keys(bodies_set(index, skip={(TASK_DOC, OBJECTIVE)}), TASK_DOC, "<!-- section: ## Objective -->\n\nGoal.\n")
    code, out = run_lint(tmp_path, capsys, bodies)
    assert code == 0, out


def test_lint_a_section_body_covers_no_marker_under_another_heading(tmp_path, capsys, index):
    skip = {(TASK_DOC, OBJECTIVE)} | under(index, TASK_DOC, "## Notes for Agent")
    bodies = add_keys(bodies_set(index, skip=skip), TASK_DOC, "<!-- section: ## Notes for Agent -->\n\nx\n")
    code, out = run_lint(tmp_path, capsys, bodies)
    assert code == 1
    assert summary(out)["S01-01"] == (1, 0)


# ---- rule: a section body may not swallow another body

def test_lint_a_fill_inside_a_section_span_exits_2(tmp_path, capsys, index):
    notes = next(m[0] for m in index[TASK_DOC]["markers"] if m[1] == "## Notes for Agent")
    code, out = run_lint(tmp_path, capsys, add_keys(bodies_set(index), TASK_DOC, "<!-- section: ## Notes for Agent -->\n\nx\n"))
    assert code == 2, out
    assert (f"LINT: doc={TASK_DOC} key=fill: {notes}: the section body of ## Notes for Agent replaces this key, "
            "so its body is lost") in out.splitlines()
    assert summary(out)["S01-01"] == (0, 1)


def test_lint_a_child_section_inside_a_parent_section_exits_2(tmp_path, capsys, index):
    parent = "## Expected Output"
    child = next(h for h in index[TASK_DOC]["headings"] if h.startswith("### References Moved"))
    keys = f"<!-- section: {parent} -->\n\nParent.\n\n<!-- section: {child} -->\n\nChild.\n"
    code, out = run_lint(tmp_path, capsys, add_keys(bodies_set(index, skip=under(index, TASK_DOC, parent)), TASK_DOC, keys))
    assert code == 2, out
    assert (f"LINT: doc={TASK_DOC} key=section: {child}: the section body of {parent} replaces this key, "
            "so its body is lost") in out.splitlines()


def test_lint_two_sections_with_separate_spans_are_accepted(tmp_path, capsys, index):
    schema, notes = "### Schema Pin", "## Notes for Agent"
    keys = f"<!-- section: {schema} -->\n\nOne.\n\n<!-- section: {notes} -->\n\nTwo.\n"
    skip = under(index, TASK_DOC, schema) | under(index, TASK_DOC, notes)
    code, out = run_lint(tmp_path, capsys, add_keys(bodies_set(index, skip=skip), TASK_DOC, keys))
    assert code == 0, out


def _overlaps(fills, sections, nested=()):
    """The lint errors of one document that holds marker `a` once under `## One` and once under `## Two`."""
    info = {"headings": ["## One", "### Sub", "## Two"], "nested": list(nested),
            "markers": [("a", "## One", None), ("a", "## Two", None)]}
    return pb.key_errors("D", {"fills": fills, "sections": sections}, info)


def test_lint_an_indexed_fill_overlaps_only_at_its_own_occurrence():
    assert len(_overlaps({("a", 1): "x"}, {"## One": "y"})) == 1
    assert _overlaps({("a", 2): "x"}, {"## One": "y"}) == []


def test_lint_a_bare_fill_with_an_occurrence_past_the_section_keeps_its_body():
    assert _overlaps({("a", None): "x"}, {"## One": "y"}) == []
    assert len(_overlaps({("a", None): "x"}, {"## One": "y", "## Two": "z"})) == 1


def test_lint_an_empty_body_overlaps_nothing():
    assert _overlaps({("a", 1): "x"}, {"## One": ""}) == []
    assert _overlaps({("a", 1): ""}, {"## One": "y"}) == []
    assert _overlaps({}, {"## One": "", "### Sub": "x"}, nested=[("### Sub", "## One")]) == []


# ---- rule: H2 outside a fence

FENCED_H2 = "```markdown\n## Not A Section\n```\n"


def test_lint_h2_inside_a_fence_is_accepted(tmp_path, capsys, index):
    skip = under(index, TASK_DOC, "## Notes for Agent")
    bodies = add_keys(bodies_set(index, skip=skip), TASK_DOC, f"<!-- section: ## Notes for Agent -->\n\n{FENCED_H2}")
    code, out = run_lint(tmp_path, capsys, bodies)
    assert code == 0, out


def test_lint_h2_outside_a_fence_names_key_and_doc(tmp_path, capsys, index):
    bodies = add_keys(bodies_set(index), TASK_DOC, "<!-- section: ## Notes for Agent -->\n\n## Not A Section\n")
    code, out = run_lint(tmp_path, capsys, bodies)
    assert code == 2
    assert (f"LINT: doc={TASK_DOC} key=section: ## Notes for Agent: H2 line outside a fence: ## Not A Section"
            in out.splitlines())


LAST_BODY = "<!-- section: ## Notes for Agent -->\n\n```text\nledger row\n"


def test_lint_fence_closed_at_end_of_file_is_accepted(tmp_path, capsys, index):
    bodies = bodies_set(index, skip=under(index, "S01-02-02", "## Notes for Agent"))
    bodies["QZX-bodies-S01-02.md"] += LAST_BODY + "```\n"
    code, out = run_lint(tmp_path, capsys, bodies)
    assert code == 0, out


def test_lint_fence_open_at_end_of_file_names_key_and_doc(tmp_path, capsys, index):
    bodies = bodies_set(index, skip=under(index, "S01-02-02", "## Notes for Agent"))
    bodies["QZX-bodies-S01-02.md"] += LAST_BODY
    code, out = run_lint(tmp_path, capsys, bodies)
    assert code == 2
    assert ("LINT: doc=S01-02-02 key=section: ## Notes for Agent: a fence is still open at the end of "
            "QZX-bodies-S01-02.md") in out.splitlines()
    assert summary(out)["S01-02"] == (0, 1)


def test_parse_keeps_a_directive_inside_a_fence_as_body_text():
    text = f"<!-- doc: {TASK_DOC} -->\n<!-- fill: Step 1 -->\n```text\n<!-- fill: Step 2 -->\n```\n"
    docs, errors = pb.parse_bodies(text)
    assert errors == []
    assert docs[TASK_DOC]["fills"] == {("Step 1", None): "```text\n<!-- fill: Step 2 -->\n```"}


def test_parse_reports_an_h2_in_the_preamble_with_no_doc():
    _docs, errors = pb.parse_bodies("# Bodies\n\n## Stray\n")
    assert errors == [(None, "doc=none key=none: H2 line outside a fence: ## Stray")]


# ---- rule: a key belongs to one block, once

def test_lint_key_outside_a_document_block_exits_2(tmp_path, capsys, index):
    bodies = bodies_set(index)
    bodies["QZX-bodies-S01-02.md"] = f"<!-- fill: {OBJECTIVE} -->\n\nx\n\n" + bodies["QZX-bodies-S01-02.md"]
    code, out = run_lint(tmp_path, capsys, bodies)
    assert code == 2
    assert summary(out)["S01-02"] == (0, 1)
    assert f"key=fill: {OBJECTIVE}: the key sits outside a document block" in out


def test_lint_key_given_twice_in_one_doc_exits_2(tmp_path, capsys, index):
    code, out = run_lint(tmp_path, capsys, add_keys(bodies_set(index), TASK_DOC, f"<!-- fill: {OBJECTIVE} -->\n\nx\n"))
    assert code == 2
    assert f"LINT: doc={TASK_DOC} key=fill: {OBJECTIVE}: the key appears twice in this doc" in out.splitlines()


# ---- discovery

def _split_part(bodies):
    """Move the last document of session 01 into a -part2 file."""
    out = dict(bodies)
    first, second = out["QZX-bodies-S01-01.md"].split("<!-- doc: S01-01-02 -->")
    out["QZX-bodies-S01-01.md"] = first
    out["QZX-bodies-S01-01-part2.md"] = "<!-- doc: S01-01-02 -->" + second
    return out


def test_discovery_merges_a_part_file(tmp_path, capsys, index):
    code, out = run_lint(tmp_path, capsys, _split_part(bodies_set(index)))
    assert code == 0, out
    assert summary(out)["S01-01"] == (0, 0)


def test_discovery_duplicate_doc_id_across_two_files_exits_2(tmp_path, capsys, index):
    bodies = bodies_set(index)
    bodies["QZX-bodies-S01-01-part2.md"] = f"<!-- doc: {TASK_DOC} -->\n"
    code, out = run_lint(tmp_path, capsys, bodies)
    assert code == 2
    assert (f"LINT: doc={TASK_DOC} key=doc: the doc id appears in both QZX-bodies-S01-01-part2.md and "
            "QZX-bodies-S01-01.md") in out.splitlines()


def test_discovery_duplicate_doc_id_in_one_file_exits_2(tmp_path, capsys, index):
    bodies = bodies_set(index)
    bodies["QZX-bodies-S01-01.md"] += f"<!-- doc: {TASK_DOC} -->\n"
    code, out = run_lint(tmp_path, capsys, bodies)
    assert code == 2
    assert f"doc={TASK_DOC} key=doc: the doc id appears twice" in out


def test_discovery_reads_only_the_plans_own_names(tmp_path, index):
    bodies = bodies_set(index)
    bodies["QZX-notes.md"] = "<!-- doc: S09-09-09 -->\n"
    bodies["ABC-bodies-S01-01.md"] = "<!-- doc: S09-09-09 -->\n"
    folder = _write_bodies(tmp_path, bodies)
    assert [p.name for p in pb.bodies_files(folder, "QZX")] == [
        "QZX-bodies-S01-01.md", "QZX-bodies-S01-02.md", "QZX-bodies-plan.md"]


def test_discovery_reads_a_crlf_file(tmp_path, capsys, index):
    bodies = {name: text.replace("\n", "\r\n") for name, text in bodies_set(index).items()}
    code, out = run_lint(tmp_path, capsys, bodies)
    assert code == 0, out


def test_lint_refuses_a_missing_bodies_folder(tmp_path):
    args = ["lint", "--spec", str(_write_spec(tmp_path)), "--bodies-dir", str(tmp_path / "absent")]
    assert pb.main(args) == 2


# ---- --session

def test_lint_session_limits_the_check_to_that_session(tmp_path, capsys, index):
    bodies = bodies_set(index, skip={("S01-02-01", OBJECTIVE)})
    code, out = run_lint(tmp_path, capsys, bodies, "--session", "S01-01")
    assert code == 0, out
    assert out.splitlines() == ["session=S01-01 keys_missing=0 errors=0"]


def test_lint_session_still_reports_its_own_missing_marker(tmp_path, capsys, index):
    bodies = bodies_set(index, skip={("S01-02-01", OBJECTIVE)})
    code, out = run_lint(tmp_path, capsys, bodies, "--session", "S01-02")
    assert code == 1
    assert out.splitlines() == ["session=S01-02 keys_missing=1 errors=0"]


def test_lint_session_not_in_the_spec_exits_2(tmp_path, capsys, index):
    code, out = run_lint(tmp_path, capsys, bodies_set(index), "--session", "S07-07")
    assert code == 2
    assert "session S07-07 is not in the spec" in out


def test_lint_as_a_process_prints_non_ascii_marker_names(tmp_path, index):
    bodies = add_keys(bodies_set(index), ORCH_DOC, "<!-- fill: Why this mode — no such marker -->\n\nx\n")
    result = run_script("lint", "--spec", str(_write_spec(tmp_path)), "--bodies-dir", str(_write_bodies(tmp_path, bodies)))
    assert result.returncode == 2, result.stderr
    assert "key=fill: Why this mode — no such marker:" in result.stdout


# ---- build helpers

MANIFEST = "QZX-build-manifest.json"
FILLED_RE = re.compile(r"; fill_remaining=(\d+);")
SCHEMA_PIN = "Schema Pin"
DOC_PATTERN = sp.template_heading_sets(TEMPLATES)["task"][0]


def spec_with_omits(task_omits=(), session_omits=()):
    spec = make_spec()
    session = spec["sprints"][0]["sessions"][0]
    if task_omits:
        session["tasks"][0]["omit_sections"] = list(task_omits)
    if session_omits:
        session["omit_sections"] = list(session_omits)
    return spec


def index_of(tmp_path, spec):
    """The doc index a build of `spec` sees, read through a spec file in its own folder."""
    folder = tmp_path / "index"
    folder.mkdir(exist_ok=True)
    return pb.render_core(str(_write_spec(folder, spec)), TEMPLATES)[2]


class Build:
    """One plan folder under tmp_path: a spec, a bodies folder, a config and an out folder."""

    def __init__(self, tmp_path, capsys, bodies, spec=None):
        self.capsys = capsys
        self.spec = _write_spec(tmp_path, spec)
        self.bodies = _write_bodies(tmp_path, bodies)
        self.config = tmp_path / "config.yaml"
        self.config.write_text("plans: plans\n", encoding="utf-8")
        (tmp_path / "Scaffold-QZX").mkdir()  # the deviation gate's Class C check wants this sibling of the out folder
        self.out = tmp_path / "Exec-QZX"
        self.manifest = tmp_path / MANIFEST

    def argv(self, *extra):
        return ["build", "--spec", str(self.spec), "--bodies-dir", str(self.bodies), "--out", str(self.out),
                "--config", str(self.config), "--skip-index", *extra]

    def run(self, *extra):
        code = pb.main(self.argv(*extra))
        return code, self.capsys.readouterr().out

    def task_file(self, session=1, number=1):
        return next(self.out.rglob(f"QZX-S01-{session:02d}-{number:02d}-*.md"))

    def orchestration(self):
        return next(self.out.rglob("QZX-S01-01-Orchestration.md"))


def deviations(root):
    """The Class A and Class B findings of a built tree."""
    return [line for cls, line in sd.scan(root, sd.load_templates(TEMPLATES)) if cls in "AB"]


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


# ---- manifest

def test_manifest_lists_a_sha256_of_every_written_file(tmp_path, capsys, index):
    build = Build(tmp_path, capsys, bodies_set(index))
    assert build.run()[0] == 0
    written = {p.relative_to(build.out).as_posix(): p for p in build.out.rglob("*") if p.is_file()}
    listed = pb.read_manifest(build.manifest)
    assert set(listed) == set(written)
    assert all(listed[rel] == hashlib.sha256(p.read_bytes()).hexdigest() for rel, p in written.items())


def test_manifest_known_good_unchanged_rebuild_exits_0(tmp_path, capsys, index):
    build = Build(tmp_path, capsys, bodies_set(index))
    assert build.run()[0] == 0
    before = build.manifest.read_bytes()
    code, out = build.run()
    assert code == 0, out
    assert build.manifest.read_bytes() == before


def test_manifest_known_bad_edited_file_exits_2_and_names_it(tmp_path, capsys, index):
    build = Build(tmp_path, capsys, bodies_set(index))
    assert build.run()[0] == 0
    target = build.task_file()
    target.write_bytes(target.read_bytes() + b"edited\n")
    edited = target.read_bytes()
    code, out = build.run()
    assert code == 2
    assert f"CHANGED: {target.relative_to(build.out).as_posix()}" in out.splitlines()
    assert "REFUSED: 1 file(s) differ" in out
    assert target.read_bytes() == edited


def test_manifest_force_overwrites_the_edited_file(tmp_path, capsys, index):
    build = Build(tmp_path, capsys, bodies_set(index))
    assert build.run()[0] == 0
    target = build.task_file()
    original = target.read_bytes()
    target.write_bytes(original + b"edited\n")
    code, out = build.run("--force")
    assert code == 0, out
    assert target.read_bytes() == original
    assert build.run()[0] == 0


def test_manifest_a_deleted_file_counts_as_changed(tmp_path, capsys, index):
    build = Build(tmp_path, capsys, bodies_set(index))
    assert build.run()[0] == 0
    target = build.task_file()
    target.unlink()
    code, out = build.run()
    assert code == 2
    assert f"CHANGED: {target.relative_to(build.out).as_posix()}" in out


def test_manifest_a_full_folder_without_a_manifest_is_refused(tmp_path, capsys, index):
    build = Build(tmp_path, capsys, bodies_set(index))
    build.out.mkdir()
    (build.out / "notes.md").write_text("mine\n", encoding="utf-8")
    code, out = build.run()
    assert code == 2
    assert "holds files" in out
    assert build.run("--force")[0] == 0
    assert (build.out / "notes.md").read_text(encoding="utf-8") == "mine\n"


def test_manifest_an_unreadable_manifest_is_refused(tmp_path, capsys, index):
    build = Build(tmp_path, capsys, bodies_set(index))
    assert build.run()[0] == 0
    build.manifest.write_text("not json", encoding="utf-8")
    code, out = build.run()
    assert code == 2
    assert f"cannot read {MANIFEST}" in out


def test_manifest_a_new_path_over_an_unlisted_file_is_refused(tmp_path, capsys, index):
    build = Build(tmp_path, capsys, bodies_set(index))
    assert build.run()[0] == 0
    listed = pb.read_manifest(build.manifest)
    rel = next(r for r in listed if r.endswith("Orchestration.md"))
    del listed[rel]
    build.manifest.write_text(json.dumps({"files": listed}), encoding="utf-8")
    code, out = build.run()
    assert code == 2
    assert f"CHANGED: {rel}" in out


def test_manifest_rewrite_after_a_later_step_keeps_the_guard_quiet(tmp_path, capsys, index):
    build = Build(tmp_path, capsys, bodies_set(index))
    assert build.run()[0] == 0
    target = build.task_file()
    target.write_bytes(target.read_bytes() + b"estimate\n")
    listed = set(pb.read_manifest(build.manifest))
    assert pb.write_manifest(build.out, build.spec) == build.manifest
    rewritten = pb.read_manifest(build.manifest)
    assert set(rewritten) == listed
    assert rewritten[target.relative_to(build.out).as_posix()] == pb.file_hash(target)
    assert build.run()[0] == 0


def test_manifest_a_task_the_spec_dropped_prints_stale_and_stays(tmp_path, capsys, index):
    build = Build(tmp_path, capsys, bodies_set(index))
    assert build.run()[0] == 0
    target = build.task_file(session=2, number=2)
    spec = make_spec()
    spec["sprints"][0]["sessions"][1]["tasks"].pop()
    _write_spec(tmp_path, spec)
    for path in build.bodies.iterdir():
        path.unlink()
    for name, text in bodies_set(index_of(tmp_path, spec)).items():
        (build.bodies / name).write_text(text, encoding="utf-8")
    code, out = build.run()
    assert code == 0, out
    assert f"STALE: {target.relative_to(build.out).as_posix()}" in out.splitlines()
    assert target.exists()
    assert target.relative_to(build.out).as_posix() not in pb.read_manifest(build.manifest)


def respec(build, tmp_path, spec):
    """Point the plan at `spec`, with bodies for exactly that spec."""
    _write_spec(tmp_path, spec)
    for path in build.bodies.iterdir():
        path.unlink()
    for name, text in bodies_set(index_of(tmp_path, spec)).items():
        (build.bodies / name).write_bytes(text.encode("utf-8"))


def dropped_build(tmp_path, capsys, index):
    """A plan built, then rebuilt without its last task. Return (build, the left file, its relative path)."""
    build = Build(tmp_path, capsys, bodies_set(index))
    assert build.run()[0] == 0
    target = build.task_file(session=2, number=2)
    spec = make_spec()
    spec["sprints"][0]["sessions"][1]["tasks"].pop()
    respec(build, tmp_path, spec)
    code, out = build.run()
    assert code == 0, out
    return build, target, target.relative_to(build.out).as_posix()


def stale_of(build):
    return json.loads(build.manifest.read_text(encoding="utf-8")).get("stale")


def test_manifest_stale_is_listed_on_every_build_until_the_file_is_gone(tmp_path, capsys, index):
    build, target, rel = dropped_build(tmp_path, capsys, index)
    digest = pb.file_hash(target)
    for _ in range(2):
        code, out = build.run()
        assert code == 0, out
        assert f"STALE: {rel}" in out.splitlines()
        assert target.exists()
        assert stale_of(build) == {rel: digest}
    target.unlink()
    code, out = build.run()
    assert code == 0, out
    assert "STALE:" not in out
    assert stale_of(build) == {}


def test_manifest_a_readded_path_matching_its_stale_hash_is_no_hand_edit(tmp_path, capsys, index):
    build, target, rel = dropped_build(tmp_path, capsys, index)
    respec(build, tmp_path, make_spec())
    code, out = build.run()
    assert code == 0, out
    assert "CHANGED:" not in out and "STALE:" not in out
    assert stale_of(build) == {}
    assert pb.read_manifest(build.manifest)[rel] == pb.file_hash(target)


def test_manifest_a_readded_path_edited_after_the_drop_is_a_hand_edit(tmp_path, capsys, index):
    build, target, rel = dropped_build(tmp_path, capsys, index)
    target.write_bytes(target.read_bytes() + b"edited\n")
    edited = target.read_bytes()
    respec(build, tmp_path, make_spec())
    code, out = build.run()
    assert code == 2
    assert f"CHANGED: {rel}" in out.splitlines()
    assert target.read_bytes() == edited


def test_manifest_a_stale_edit_with_no_readd_stays_on_the_stale_list(tmp_path, capsys, index):
    build, target, rel = dropped_build(tmp_path, capsys, index)
    target.write_bytes(target.read_bytes() + b"edited\n")
    code, out = build.run()
    assert code == 0, out
    assert f"STALE: {rel}" in out.splitlines()
    assert target.read_bytes().endswith(b"edited\n")


# ---- a write that stops part-way

def blocked_rel(rendered):
    """A file late in the write order, and the number of files that land before it."""
    rels = list(rendered)
    rel = next(r for r in rels if "QZX-S01-02-01-" in r)
    return rel, rels.index(rel)


def test_write_failure_exits_3_and_says_how_many_files_landed(tmp_path, capsys, index, rendered):
    build = Build(tmp_path, capsys, bodies_set(index))
    rel, landed = blocked_rel(rendered)
    (build.out / rel).mkdir(parents=True)  # a folder in the way of a file
    code, out = build.run("--force")
    assert code == 3, out
    assert f"FAILED: the write stopped after {landed} of {len(rendered)} files (" in out
    assert "REFUSED" not in out and "gate=" not in out
    assert out.rstrip().endswith("exit=3")
    assert set(pb.read_manifest(build.manifest)) == set(list(rendered)[:landed])


def test_write_failure_manifest_clears_the_landed_files_for_the_next_build(tmp_path, capsys, index, rendered):
    build = Build(tmp_path, capsys, bodies_set(index))
    rel, _landed = blocked_rel(rendered)
    (build.out / rel).mkdir(parents=True)
    assert build.run("--force")[0] == 3
    (build.out / rel).rmdir()
    code, out = build.run()
    assert code == 0, out
    assert "CHANGED:" not in out


def test_write_failure_manifest_still_tells_a_hand_edit_from_a_landed_file(tmp_path, capsys, index, rendered):
    build = Build(tmp_path, capsys, bodies_set(index))
    rel, _landed = blocked_rel(rendered)
    (build.out / rel).mkdir(parents=True)
    assert build.run("--force")[0] == 3
    (build.out / rel).rmdir()
    first = next(iter(rendered))
    (build.out / first).write_bytes((build.out / first).read_bytes() + b"edited\n")
    code, out = build.run()
    assert code == 2
    assert [ln for ln in out.splitlines() if ln.startswith("CHANGED:")] == [f"CHANGED: {first}"]


def test_write_failure_on_a_rebuild_keeps_the_earlier_entries_of_unreached_files(tmp_path, capsys, index, rendered):
    build = Build(tmp_path, capsys, bodies_set(index))
    assert build.run()[0] == 0
    before = pb.read_manifest(build.manifest)
    rel, _landed = blocked_rel(rendered)
    (build.out / rel).unlink()
    (build.out / rel).mkdir()
    assert build.run("--force")[0] == 3
    after = pb.read_manifest(build.manifest)
    assert set(after) == set(before)
    assert after[rel] == before[rel]


def test_write_failure_in_the_first_manifest_write_exits_3(tmp_path, capsys, index, rendered, monkeypatch):
    def refuse(*_args):
        raise OSError("disk full")

    monkeypatch.setattr(pb, "write_manifest", refuse)
    build = Build(tmp_path, capsys, bodies_set(index))
    code, out = build.run()
    assert code == 3, out
    assert f"after {len(rendered)} of {len(rendered)} files (OSError: disk full)" in out
    assert set(pb.read_manifest(build.manifest)) == set(rendered)


# ---- module docstring

def test_docstring_names_the_one_template_text_the_module_holds():
    opening = pb.__doc__.split("Commands (run")[0]
    assert "FIRST_KEPT_LINES" in opening
    assert "It carries no template text of its own." not in opening
