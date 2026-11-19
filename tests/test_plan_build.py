"""Tests for scripts/plan_build.py: one known-good and one known-bad case per rule.

Marker names and headings come from a real render of the templates, never from invented rows.
"""

import copy
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
        "number": number, "name": name, "title": f"Step {number} of the ledger", "agent": agent, "estimate_k": 20 + number,
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
    spec["meta"] = False
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
    # the fixture task holds one 1.5K read row plus output_k 4 and working_k 6: round(11.5) is 12
    assert core["sprints"][0]["sessions"][0]["tasks"][0]["estimate_k"] == round(1.5 + 4 + 6) == 12
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


def _keys_blocks(stdout):
    """{doc id: (markers=<n> figure, sum of its marker count= figures)} from `keys` output."""
    blocks, doc = {}, None
    for line in stdout.splitlines():
        if line.startswith("doc "):
            doc = line.split()[1]
            blocks[doc] = [int(line.rsplit("markers=", 1)[1]), 0]
        elif line.startswith("  marker "):
            blocks[doc][1] += int(line.rsplit("count=", 1)[1])
    return blocks


def test_keys_session_prints_only_that_sessions_docs_with_a_matching_total(tmp_path):
    spec_path = str(_write_spec(tmp_path))
    whole = run_script("keys", "--spec", spec_path)
    one = run_script("keys", "--spec", spec_path, "--session", "S01-01")
    assert one.returncode == 0, one.stdout + one.stderr
    blocks = _keys_blocks(one.stdout)
    assert sorted(blocks) == ["S01-01-01", "S01-01-02", "S01-01-ORCH", "S01-01-RECOVERY"]
    assert all(figure == counted for figure, counted in blocks.values())
    # each shown block is byte-identical to the same block of the whole-plan run
    whole_blocks = _keys_blocks(whole.stdout)
    assert all(blocks[doc] == whole_blocks[doc] for doc in blocks)
    total = sum(figure for figure, _counted in blocks.values())
    assert total < sum(figure for figure, _counted in whole_blocks.values())
    assert one.stdout.splitlines()[-1] == f"fill_markers={total} docs=4"


def test_keys_session_plan_prints_only_the_plan_documents(tmp_path):
    result = run_script("keys", "--spec", str(_write_spec(tmp_path)), "--session", pb.PLAN_GROUP)
    assert result.returncode == 0, result.stdout + result.stderr
    blocks = _keys_blocks(result.stdout)
    assert blocks and all(pb.session_of(doc) == pb.PLAN_GROUP for doc in blocks)
    assert result.stdout.splitlines()[-1] == f"fill_markers={sum(f for f, _c in blocks.values())} docs={len(blocks)}"


def test_keys_unknown_session_exits_2_with_a_refused_line(tmp_path):
    result = run_script("keys", "--spec", str(_write_spec(tmp_path)), "--session", "S09-09")
    assert result.returncode == 2
    assert result.stdout.startswith("REFUSED: session S09-09 is not in the spec. Fix: pass a session such as S01-01.")
    assert not any(ln.startswith("doc ") for ln in result.stdout.splitlines())


@pytest.mark.parametrize("command", ["keys", "lint", "build"])
def test_each_command_reads_the_spec_file_once(tmp_path, capsys, monkeypatch, index, command):
    build = Build(tmp_path, capsys, bodies_set(index))
    argv = {"keys": ["keys", "--spec", str(build.spec)],
            "lint": ["lint", "--spec", str(build.spec), "--bodies-dir", str(build.bodies)],
            "build": build.argv()}[command]
    reads, real = [], sp.load_spec
    monkeypatch.setattr(sp, "load_spec", lambda path: reads.append(str(path)) or real(path))
    assert pb.main(argv) == 0, capsys.readouterr().out
    assert reads == [str(build.spec)]


# A spec that json.loads cannot turn into a value: an integer past the 4,300-digit conversion limit
# (ValueError), nesting deeper than the recursion limit (RecursionError), and plain malformed text.
UNPARSEABLE_SPECS = {"huge-int": "1" * 5000, "deep-nesting": "[" * 100000, "bad": "{bad"}


@pytest.mark.parametrize("payload", UNPARSEABLE_SPECS.values(), ids=UNPARSEABLE_SPECS.keys())
@pytest.mark.parametrize("command", ["keys", "lint", "build"])
def test_spec_load_errors_refuse_keys_lint_and_build(tmp_path, command, payload):
    spec = tmp_path / "spec.json"
    spec.write_text(payload, encoding="utf-8")
    args = [command, "--spec", str(spec)]
    if command in ("lint", "build"):
        args += ["--bodies-dir", str(_write_bodies(tmp_path, bodies_set({})))]
    if command == "build":
        config = tmp_path / "config.yaml"
        config.write_text("plans: plans\n", encoding="utf-8")
        args += ["--out", str(tmp_path / "Exec-QZX"), "--config", str(config), "--skip-index"]
    result = run_script(*args)
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert "REFUSED: cannot read spec" in result.stdout
    assert "Fix: pass a readable UTF-8 JSON spec." in result.stdout
    assert "Traceback" not in result.stderr


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


# ---- meta plans

META = "ZCPL"
PLAN_DIR = ("Plans", "OrchardLedger")
PLAIN_SITES = (f"{META}-Master-Plan", "{Abbrev}-S{XX}-Sprint-Plan")  # the two forms a render prints
META_SITES = (f"{META}-META-Master-Plan", "{Abbrev}-META-S{XX}-Sprint-Plan")
META_OUTPUT = f"Outputs/{META}-META-S01-01-01-Parse.md"
GATE_LINE_RE = re.compile(r"^gate=(\w+) status=(\w+) files=(\d+) (.*)$", re.MULTILINE)


def meta_spec(meta=True):
    """The sample spec as a Meta plan: every session DELEGATED, every session output named with the prefix."""
    spec = make_spec()
    spec.update(abbrev=META, meta=meta)
    sprint = spec["sprints"][0]
    sprint["name"] = "X"
    sprint["sessions"][1]["mode"] = "DELEGATED"
    sprint["sessions"][0]["tasks"][0]["outputs"] = ["src/orchard/parse.py", META_OUTPUT]
    sprint["sessions"][1]["tasks"][1]["outputs"] = [f"Outputs/{META}-META-S01-02-02-Verify.md"]
    return spec


def direct_session_spec(meta=True):
    spec = meta_spec(meta)
    spec["sprints"][0]["sessions"][1]["mode"] = "DIRECT"
    return spec


def plain_output_spec(meta=True):
    spec = meta_spec(meta)
    spec["sprints"][0]["sessions"][0]["tasks"][0]["outputs"] = ["src/orchard/parse.py", f"Outputs/{META}-parse.md"]
    return spec


def meta_build(tmp_path, capsys, spec=None, bodies=None):
    """A meta plan under tmp_path, with its out folder inside the `Plans` folder the index step reads."""
    if bodies is None:
        bodies = bodies_set(index_of(tmp_path, meta_spec()))
    build = Build(tmp_path, capsys, {n.replace("QZX-", f"{META}-"): t for n, t in bodies.items()}, spec or meta_spec())
    build.config.write_text("project_name: Chain\n", encoding="utf-8")
    build.out = tmp_path.joinpath(*PLAN_DIR)
    build.root = build.out / f"Meta-{META}"
    build.manifest = tmp_path / f"{META}{'-META' if pb.is_meta(spec or meta_spec()) else ''}-build-manifest.json"
    context = tmp_path / "src" / "orchard" / "ledger.py"  # on disk, so the estimates gate rewrites every task file
    context.parent.mkdir(parents=True)
    context.write_bytes(b"x = 1\n" * 900)
    return build


def full_run(build):
    """Run `build` with all five gates, the index step included."""
    code = pb.main([arg for arg in build.argv() if arg != "--skip-index"])
    return code, build.capsys.readouterr().out


def tree_files(root):
    return {p.relative_to(root).as_posix(): p for p in root.rglob("*") if p.is_file()}


def token_count(root, token):
    """Occurrences of `token` in the Markdown files under `root`. Return (count, files read)."""
    texts = [p.read_text(encoding="utf-8") for p in root.rglob("*.md")]
    return sum(t.count(token) for t in texts), len(texts)


# ---- module docstring

def test_docstring_names_the_one_template_text_the_module_holds():
    opening = pb.__doc__.split("Commands (run")[0]
    assert "FIRST_KEPT_LINES" in opening
    assert "It carries no template text of its own." not in opening


def test_docstring_report_section_names_no_line_a_built_report_never_prints():
    assert "CHANGED" not in pb.__doc__.split("Report. `build` prints")[1]


def test_docstring_counts_only_the_keys_scaffold_plan_does_not_know():
    key_list = pb.__doc__.split("Build spec format.")[1].split("meta           plan level")[0]
    assert "four keys" in key_list and "five keys" not in key_list
    assert all(f"`{key}`" in key_list for key in pb.BUILD_KEYS)


def test_docstring_records_no_nested_meta_folder():
    assert "nests a second folder" not in pb.__doc__
