"""Tests for the Meta plan switch of scripts/plan_build.py.

Shared helpers live in `tests/test_plan_build.py`.
"""

import json
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
    GATE_LINE_RE,
    META,
    META_SITES,
    ORCH_DOC,
    PLAIN_SITES,
    PLAN_DIR,
    TASK_DOC,
    TEMPLATES,
    _build_owned_spec,
    _write_spec,
    add_keys,
    bodies_set,
    deviations,
    direct_session_spec,
    full_run,
    index_of,
    make_spec,
    meta_build,
    meta_spec,
    plain_output_spec,
    token_count,
    tree_files,
    under,
)


def test_meta_known_good_renders_the_names_the_gitkeep_and_the_tokens(tmp_path, capsys):
    build = meta_build(tmp_path, capsys)
    code, out = full_run(build)
    assert code == 0, out
    files = tree_files(build.root)
    assert {f"{META}-META-Master-Plan.md", f"Sprint-01-X/{META}-META-S01-Sprint-Plan.md", "Outputs/.gitkeep"} <= set(files)
    assert f"{META}-Master-Plan.md" not in files and f"Sprint-01-X/{META}-S01-Sprint-Plan.md" not in files
    session = f"Sprint-01-X/Session-01-ReadPath/{META}-S01-01"
    assert {f"{session}-Orchestration.md", f"{session}-Recovery.md"} <= set(files)  # structural files keep plain names
    assert not [rel for rel in tree_files(build.out) if not rel.startswith(f"Meta-{META}/")]
    for token in PLAIN_SITES:
        assert token_count(build.root, token) == (0, 10), token
    for token in META_SITES:
        assert token_count(build.root, token)[0] >= 1, token


def test_meta_control_a_standard_build_holds_the_plain_tokens(tmp_path, capsys):
    build = meta_build(tmp_path, capsys, meta_spec(meta=False))
    code, out = build.run()
    assert code == 0, out
    for token in PLAIN_SITES:
        assert token_count(build.out, token)[0] >= 1, token
    for token in META_SITES:
        assert token_count(build.out, token) == (0, 10), token


def test_meta_rewrite_reaches_a_body_and_spares_another_plans_token(tmp_path, capsys):
    index = index_of(tmp_path, meta_spec())
    line = f"See {META}-Master-Plan.md and ../{META}-S01-Sprint-Plan.md, not X{META}-Master-Plan.md."
    keys = f"<!-- section: ## Notes for Agent -->\n\n{line}\n"
    bodies = add_keys(bodies_set(index, skip=under(index, TASK_DOC, "## Notes for Agent")), TASK_DOC, keys)
    build = meta_build(tmp_path, capsys, bodies=bodies)
    code, out = build.run()
    assert code == 0, out
    text = next(build.root.rglob(f"{META}-S01-01-01-*.md")).read_text(encoding="utf-8")
    assert (f"See {META}-META-Master-Plan.md and ../{META}-META-S01-Sprint-Plan.md, "
            f"not X{META}-Master-Plan.md.") in text


def test_meta_full_chain_runs_on_the_renamed_tree_and_exits_0(tmp_path, capsys):
    build = meta_build(tmp_path, capsys)
    code, out = full_run(build)
    assert code == 0, out
    found = GATE_LINE_RE.findall(out)
    assert [g[0] for g in found] == ["estimates", "headings", "deviations", "scan", "index"]
    assert {g[1] for g in found} == {"ok"}, out
    assert {int(g[2]) for g in found} == {len(tree_files(build.root))}
    assert found[0][3] == "sessions=2 tasks=4 failed=0"
    assert out.rstrip().endswith("fill_remaining=0\nexit=0")
    assert f"built {len(tree_files(build.root))} files to {build.root};" in out
    index = (tmp_path / "Plans" / "00-Index-Plans.md").read_text(encoding="utf-8")
    assert "OrchardLedger (Meta / Discovery)" in index and META in index


def exec_sibling(tmp_path):
    """An Exec plan with the Meta plan's abbreviation, at a depth the index walk reads."""
    master = tmp_path.joinpath(*PLAN_DIR, f"Exec-{META}", f"{META}-Master-Plan.md")
    master.parent.mkdir(parents=True)
    master.write_text(f"# {META} Master Plan\n\n**Status:** NOT_STARTED\n**Created:** 2026-01-02\n"
                      f"**Last Updated:** 2026-01-03\n", encoding="utf-8")


def index_gate(out):
    return next(g for g in GATE_LINE_RE.findall(out) if g[0] == "index")


def test_meta_index_gate_reports_a_meta_tree_the_walk_misses_beside_an_exec_row(tmp_path, capsys):
    build = meta_build(tmp_path, capsys)
    build.out = tmp_path.joinpath(*PLAN_DIR, "Drafts")  # the Meta root sits at depth 3, which the walk ignores
    build.root = build.out / f"Meta-{META}"
    exec_sibling(tmp_path)
    _code, out = full_run(build)
    index = (tmp_path / "Plans" / "00-Index-Plans.md").read_text(encoding="utf-8")
    assert "OrchardLedger (Exec)" in index and "(Meta / Discovery)" not in index
    assert index_gate(out)[1] == "finding", out
    assert "holds no row for ZCPL at OrchardLedger/Drafts/Meta-ZCPL/" in out


def test_meta_index_gate_passes_a_reached_meta_tree_beside_an_exec_row(tmp_path, capsys):
    build = meta_build(tmp_path, capsys)
    exec_sibling(tmp_path)
    code, out = full_run(build)
    assert code == 0, out
    index = (tmp_path / "Plans" / "00-Index-Plans.md").read_text(encoding="utf-8")
    assert "OrchardLedger (Meta / Discovery)" in index and "OrchardLedger (Exec)" in index
    assert index_gate(out)[1] == "ok", out


def test_meta_headings_gate_counts_the_renamed_plan_files(tmp_path, capsys):
    build = meta_build(tmp_path, capsys)
    assert build.run()[0] == 0
    kinds = {Path(r["path"]).name: r for r in sp.check_headings([build.root], TEMPLATES)}
    for name, kind in ((f"{META}-META-Master-Plan.md", "master"), (f"{META}-META-S01-Sprint-Plan.md", "sprint")):
        assert kinds[name]["kind"] == kind and kinds[name]["h2"] > 0


@pytest.mark.parametrize("name,old,new,reported", [
    (f"{META}-META-Master-Plan.md", "**Total Sessions:**", "Sessions:", "CLASS_B"),
    (f"{META}-META-S01-Sprint-Plan.md", "## Sessions", "## Rounds", "CLASS_A"),
], ids=["master", "sprint"])
def test_meta_deviation_gate_grades_a_renamed_plan_file(tmp_path, capsys, name, old, new, reported):
    build = meta_build(tmp_path, capsys)
    assert build.run()[0] == 0
    assert deviations(build.root) == []
    target = next(build.root.rglob(name))
    text = target.read_text(encoding="utf-8")
    assert old in text
    target.write_text(text.replace(old, new), encoding="utf-8")
    assert [line for line in deviations(build.root) if line.startswith(f"{reported} ") and name in line]


def test_meta_scan_gate_reads_the_task_files_under_the_meta_root(tmp_path, capsys):
    spec = meta_spec()
    for task in spec["sprints"][0]["sessions"][0]["tasks"]:
        task["required_context"] = [{"priority": 1, "path": "src/big.py", "kib": 108.0, "tokens_k": 30.0,
                                     "purpose": "the big module"}]
    build = meta_build(tmp_path, capsys, spec, bodies_set(index_of(tmp_path, spec)))
    build.config.write_text("plans: plans\ncontext:\n  token_saver: true\n", encoding="utf-8")
    (tmp_path / "src" / "big.py").write_bytes(b"x = 1\n" * 18_500)  # about 110 KB
    code, out = build.run()
    assert code == 1, out
    scan = next(g for g in GATE_LINE_RE.findall(out) if g[0] == "scan")
    assert scan[1] == "finding" and scan[3].endswith("exit=1"), out


def test_meta_manifest_covers_the_renamed_paths_and_a_second_build_exits_0(tmp_path, capsys):
    build = meta_build(tmp_path, capsys)
    assert full_run(build)[0] == 0
    files, listed = tree_files(build.root), pb.read_manifest(build.manifest)
    assert set(listed) == set(files)
    assert all(listed[rel] == pb.file_hash(path) for rel, path in files.items())
    code, out = full_run(build)
    assert code == 0, out
    assert "CHANGED:" not in out and "STALE:" not in out
    assert pb.read_manifest(build.manifest) == listed


def test_meta_manifest_guard_sees_an_edit_to_a_renamed_file(tmp_path, capsys):
    build = meta_build(tmp_path, capsys)
    assert build.run()[0] == 0
    rel = f"Sprint-01-X/{META}-META-S01-Sprint-Plan.md"
    (build.root / rel).write_bytes((build.root / rel).read_bytes() + b"edited\n")
    code, out = build.run()
    assert code == 2
    assert f"CHANGED: {rel}" in out.splitlines()


def test_meta_known_bad_direct_session_exits_2_naming_it(tmp_path, capsys):
    build = meta_build(tmp_path, capsys, direct_session_spec())
    code, out = build.run()
    assert code == 2, out
    assert "LINT: session S01-02: mode is DIRECT, and a meta plan session must be DELEGATED" in out.splitlines()
    assert not build.out.exists() and not build.manifest.exists()


def test_meta_known_bad_plain_output_exits_2_naming_the_task(tmp_path, capsys):
    build = meta_build(tmp_path, capsys, plain_output_spec())
    code, out = build.run()
    assert code == 2, out
    assert (f'LINT: task S01-01-01: output "Outputs/{META}-parse.md" must start with {META}-META-S01-01-'
            in out.splitlines())
    assert not build.out.exists() and not build.manifest.exists()


@pytest.mark.parametrize("make", [direct_session_spec, plain_output_spec], ids=["direct", "plain-output"])
def test_meta_lint_and_keys_refuse_the_same_spec(tmp_path, capsys, make):
    build = meta_build(tmp_path, capsys, make())
    assert pb.main(["keys", "--spec", str(build.spec)]) == 2
    assert pb.main(["lint", "--spec", str(build.spec), "--bodies-dir", str(build.bodies)]) == 2
    assert capsys.readouterr().out.count("meta plan error(s)") == 2


@pytest.mark.parametrize("make", [direct_session_spec, plain_output_spec], ids=["direct", "plain-output"])
def test_meta_false_renders_the_same_fixture_as_a_standard_plan(tmp_path, capsys, make):
    build = meta_build(tmp_path, capsys, make(meta=False))
    code, out = build.run()
    assert code == 0, out
    files = tree_files(build.out)
    assert {f"{META}-Master-Plan.md", f"Sprint-01-X/{META}-S01-Sprint-Plan.md"} <= set(files)
    assert not build.root.exists() and "Outputs/.gitkeep" not in files


def test_meta_known_bad_a_string_value_exits_2_naming_the_key(tmp_path, capsys):
    spec = meta_spec()
    spec["meta"] = "true"
    build = meta_build(tmp_path, capsys, spec)
    code, out = build.run()
    assert code == 2, out
    assert 'LINT: plan level: meta must be true or false, got "true"' in out.splitlines()
    assert not build.out.exists() and not build.manifest.exists()


def test_meta_control_a_false_value_renders_a_standard_plan(tmp_path, capsys):
    build = meta_build(tmp_path, capsys, meta_spec(meta=False))
    code, out = build.run()
    assert code == 0, out
    assert f"{META}-Master-Plan.md" in tree_files(build.out)
    assert not build.root.exists()


def test_meta_only_a_true_value_is_the_switch(tmp_path, capsys):
    spec = _build_owned_spec()
    assert not pb.is_meta(spec)
    assert not pb.is_meta(make_spec())
    assert pb.is_meta(meta_spec())
    assert pb.render_core(str(_write_spec(tmp_path, spec)), TEMPLATES) is not None
    assert "LINT" not in capsys.readouterr().out


def test_meta_the_core_spec_never_sees_the_key_and_doc_ids_stay_plain(tmp_path):
    core, _files, idx = pb.render_core(str(_write_spec(tmp_path, meta_spec())), TEMPLATES)
    assert "meta" not in core
    assert list(idx)[:3] == ["MASTER", "S01", ORCH_DOC]


@pytest.mark.parametrize("path,errors", [
    (f"Outputs/{META}-META-S01-01-01-Parse.md", 0),
    (f"Outputs/{META}-META-S01-02-01-Parse.md", 1),  # the prefix of another session
    (f"Outputs/{META}-S01-01-Summary.md", 1),
    (f"plans/Meta-{META}/Sprint-01-X/Session-01-ReadPath/Outputs/{META}-parse.md", 1),
    (f"plans/Meta-{META}/Sprint-01-X/Session-01-ReadPath/Outputs/{META}-META-S01-01-01-Parse.md", 0),
    (f"plans\\Meta-{META}\\Sprint-01-X\\Session-01-ReadPath\\Outputs\\{META}-parse.md", 1),
    (f"plans/Meta-{META}/Outputs/{META}-Consolidated-Context-Part-1-Topic.md", 0),  # the plan-level folder
    (f"Meta-{META}/Outputs/{META}-Probe-Ledger.md", 0),
    ("src/orchard/parse.py", 0),
], ids=["own-prefix", "other-session", "summary", "full-plain", "full-prefix", "backslash", "plan-level", "plan-level-root",
        "no-outputs-folder"])
def test_meta_output_rule_reads_the_session_outputs_folder_only(path, errors):
    spec = meta_spec()
    spec["sprints"][0]["sessions"][0]["tasks"][0]["outputs"] = [path]
    assert len(pb.meta_errors(spec)) == errors


@pytest.mark.parametrize("path", [f"../../Outputs/{META}-Probe-Ledger.md", f"..\\..\\Outputs\\{META}-Probe-Ledger.md"],
                         ids=["slash", "backslash"])
def test_meta_output_rule_reads_a_relative_path_from_the_session_folder(path):
    spec = meta_spec()
    spec["sprints"][0]["sessions"][0]["tasks"][0]["outputs"] = [path]
    assert pb.meta_errors(spec) == []
    spec["sprints"][0]["sessions"][0]["tasks"][0]["outputs"] = [f"../Outputs/{META}-parse.md"]  # a sprint folder, so no exemption
    assert len(pb.meta_errors(spec)) == 1


@pytest.mark.parametrize("text", [
    f"[plan](../../Exec-{META}/{META}-Master-Plan.md)",
    f"Exec-{META}/Sprint-01-X/{META}-S01-Sprint-Plan.md",
    f"Exec-{META}\\{META}-Master-Plan.md",
    f"{META}-Master-Plan-Notes.md",
    f"{META}-S01-Sprint-Plan-Draft.md",
], ids=["exec-link", "exec-sprint", "exec-backslash", "longer-master", "longer-sprint"])
def test_meta_rewrite_leaves_an_exec_path_and_a_longer_name_alone(text):
    assert pb.meta_tree({"a.md": text}, META)["a.md"] == text


def test_meta_rewrite_still_reaches_a_bare_token_beside_an_exec_path():
    text = f"Exec-{META}/{META}-Master-Plan.md, then {META}-Master-Plan.md and ../{META}-S01-Sprint-Plan.md"
    assert pb.meta_tree({"a.md": text}, META)["a.md"] == (
        f"Exec-{META}/{META}-Master-Plan.md, then {META}-META-Master-Plan.md and ../{META}-META-S01-Sprint-Plan.md")


def test_meta_and_exec_specs_in_one_folder_keep_their_own_manifests(tmp_path, capsys):
    build = meta_build(tmp_path, capsys)
    exec_spec, exec_out = tmp_path / "exec.json", build.out / f"Exec-{META}"
    exec_spec.write_text(json.dumps(meta_spec(meta=False)), encoding="utf-8")
    (build.out / f"Scaffold-{META}").mkdir(parents=True)

    def run_exec():
        swap = {str(build.spec): str(exec_spec), str(build.out): str(exec_out)}
        code = pb.main([swap.get(arg, arg) for arg in build.argv()])
        return code, capsys.readouterr().out

    assert build.run()[0] == 0
    code, out = run_exec()
    assert code == 0, out
    assert "CHANGED:" not in out
    assert build.run("--force")[0] == 0  # the Meta build must not take the Exec tree's guard with it
    assert f"{META}-Master-Plan.md" in pb.read_manifest(tmp_path / f"{META}-build-manifest.json")
    assert f"{META}-META-Master-Plan.md" in pb.read_manifest(tmp_path / f"{META}-META-build-manifest.json")
    edited = exec_out / f"{META}-Master-Plan.md"
    edited.write_bytes(edited.read_bytes() + b"edited\n")
    code, out = run_exec()
    assert code == 2
    assert f"CHANGED: {META}-Master-Plan.md" in out.splitlines()


@pytest.mark.parametrize("extra", [(), ("--force",)], ids=["guarded", "force"])
def test_meta_refuses_an_out_that_already_ends_in_the_meta_folder(tmp_path, capsys, extra):
    build = meta_build(tmp_path, capsys)
    build.out = build.root
    code, out = build.run(*extra)
    assert code == 2, out
    assert len(out.splitlines()) == 1 and out.startswith("REFUSED: ") and f"Meta-{META}" in out
    assert not build.root.exists() and not build.manifest.exists()


@pytest.mark.parametrize("extra", [(), ("--force",)], ids=["guarded", "force"])
def test_meta_refuses_a_root_path_that_is_a_file(tmp_path, capsys, extra):
    build = meta_build(tmp_path, capsys)
    build.out.mkdir(parents=True)
    build.root.write_text("mine\n", encoding="utf-8")
    code, out = build.run(*extra)
    assert code == 2
    assert out.splitlines() == [f"REFUSED: {build.root} is not a folder. Fix: pass a folder for --out."]
    assert build.root.read_text(encoding="utf-8") == "mine\n"
