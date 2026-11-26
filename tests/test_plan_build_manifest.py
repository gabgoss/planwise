"""Tests for the build manifest and the part-way write failure of scripts/plan_build.py.

Shared helpers live in `tests/test_plan_build.py`.
"""

import hashlib
import json
import shutil
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
    MANIFEST,
    SCHEMA_PIN,
    SUMMARY_RE,
    TASK_DOC,
    TEMPLATES,
    Build,
    _write_spec,
    add_keys,
    bodies_set,
    index_of,
    make_spec,
    spec_with_omits,
)


@pytest.fixture(scope="module")
def rendered():
    return sp.render_all(make_spec(), TEMPLATES)[0]


@pytest.fixture(scope="module")
def index(rendered):
    return pb.doc_index(rendered, TEMPLATES)


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


# ---- the marker record: a marker that is new since the last build

OBJECTIVE = "2-3 sentences describing what this session accomplishes"  # a token of the real Orchestration template, which the spec fills
GAINED = "Marker a later release adds"
ORCH_DOCS = ("S01-01-ORCH", "S01-02-ORCH")
ADDED_TAIL = "(new since the last build: the template or the spec added it)"


def templates_copy(tmp_path):
    """A byte copy of the shipped templates, so a test can change one the way a release does."""
    copy = tmp_path / "templates"
    shutil.copytree(TEMPLATES, copy)
    return copy


def gain_markers(templates, *names):
    """Add one brace token per name to the Orchestration template, under the session objective's own token."""
    path = templates / "orchestration.md"
    data = path.read_bytes()
    eol = b"\r\n" if b"\r\n" in data else b"\n"
    anchor = f"{{{OBJECTIVE}}}".encode()
    assert data.count(anchor) == 1
    added = b"".join(eol + eol + f"{{{name}}}".encode() for name in names)
    path.write_bytes(data.replace(anchor, anchor + added))


def lint(build, *extra):
    code = pb.main(["lint", "--spec", str(build.spec), "--bodies-dir", str(build.bodies), *extra])
    return code, build.capsys.readouterr().out


def rewrite_bodies(build, bodies):
    for name, text in bodies.items():
        (build.bodies / name).write_bytes(text.encode("utf-8"))


def test_markers_the_first_build_records_every_marker_name_of_every_doc(tmp_path, capsys, index):
    build = Build(tmp_path, capsys, bodies_set(index))
    assert build.run()[0] == 0
    assert pb.read_markers(build.manifest) == {doc: sorted({m[0] for m in info["markers"]}) for doc, info in index.items()}


def test_markers_a_marker_the_template_gains_prints_added(tmp_path, capsys, index):
    build = Build(tmp_path, capsys, bodies_set(index))
    templates = templates_copy(tmp_path)
    code, out = build.run("--templates", str(templates))
    assert code == 0, out
    code, out = lint(build, "--templates", str(templates))
    assert code == 0 and "ADDED:" not in out, out  # control: the unchanged copy lints clean
    gain_markers(templates, GAINED)
    code, out = lint(build, "--templates", str(templates))
    lines = out.splitlines()
    assert code == 1, out
    for doc in ORCH_DOCS:
        assert f"ADDED: doc={doc} marker={GAINED} [1] {ADDED_TAIL}" in lines, out
        assert any(ln.startswith(f"MISSING: doc={doc} marker={GAINED} [1] under ") for ln in lines), out
    assert "added_since_build=2" in lines
    assert SUMMARY_RE.fullmatch(lines[-1]), out  # the summary lines stay last
    assert "holds no marker record" not in out


def test_markers_added_lines_are_capped_per_group(tmp_path, capsys, index, monkeypatch):
    build = Build(tmp_path, capsys, bodies_set(index))
    templates = templates_copy(tmp_path)
    assert build.run("--templates", str(templates))[0] == 0
    gain_markers(templates, GAINED, "A second marker the release adds")
    monkeypatch.setattr(pb, "DETAIL_LIMIT", 1)
    _code, out = lint(build, "--templates", str(templates))
    lines = out.splitlines()
    assert lines.count("ADDED: +1 more") == len(ORCH_DOCS), out
    assert "added_since_build=4" in lines


def first_marker(index, doc=ORCH_DOCS[0]):
    return index[doc]["markers"][0][0]


def test_markers_a_marker_unwritten_at_the_first_build_prints_missing_only(tmp_path, capsys, index):
    unwritten = first_marker(index)
    build = Build(tmp_path, capsys, bodies_set(index, skip={(ORCH_DOCS[0], unwritten)}))
    code, out = build.run()
    assert code == 1, out
    assert "ADDED:" not in out
    code, out = lint(build)
    assert code == 1, out
    assert any(ln.startswith(f"MISSING: doc={ORCH_DOCS[0]} marker={unwritten} [1] under ") for ln in out.splitlines()), out
    assert "ADDED:" not in out and "added_since_build=" not in out and "holds no marker record" not in out


def test_markers_a_rebuild_keeps_an_unwritten_added_marker_added_until_it_has_a_body(tmp_path, capsys, index):
    bodies = bodies_set(index)
    build = Build(tmp_path, capsys, bodies)
    templates = templates_copy(tmp_path)
    assert build.run("--templates", str(templates))[0] == 0
    gain_markers(templates, GAINED)
    code, out = build.run("--templates", str(templates))
    assert code == 1, out
    for doc in ORCH_DOCS:
        assert f"ADDED: doc={doc} marker={GAINED} [1] {ADDED_TAIL}" in out.splitlines(), out
    assert "added_since_build=2" in out.splitlines()
    assert out.rstrip().endswith("exit=1")
    assert all(GAINED not in names for names in pb.read_markers(build.manifest).values())
    code, out = lint(build, "--templates", str(templates))
    assert code == 1 and "added_since_build=2" in out.splitlines(), out
    for doc in ORCH_DOCS:
        bodies = add_keys(bodies, doc, f"<!-- fill: {GAINED} -->\n\nBody for the new marker.\n")
    rewrite_bodies(build, bodies)
    code, out = lint(build, "--templates", str(templates))
    assert code == 0, out
    assert "ADDED:" not in out and "added_since_build=" not in out
    code, out = build.run("--templates", str(templates))
    assert code == 0, out
    assert "ADDED:" not in out
    recorded = pb.read_markers(build.manifest)
    assert all(GAINED in recorded[doc] for doc in ORCH_DOCS)


def test_markers_a_manifest_with_no_record_prints_the_note_and_no_added_line(tmp_path, capsys, index):
    build = Build(tmp_path, capsys, bodies_set(index))
    templates = templates_copy(tmp_path)
    assert build.run("--templates", str(templates))[0] == 0
    data = json.loads(build.manifest.read_text(encoding="utf-8"))
    del data["markers"]  # the shape every build before the marker record wrote
    build.manifest.write_text(json.dumps(data), encoding="utf-8")
    code, out = lint(build, "--templates", str(templates))
    assert code == 0 and "NOTE:" not in out, out  # nothing is missing, so there is nothing to explain
    gain_markers(templates, GAINED)
    code, out = lint(build, "--templates", str(templates))
    lines = out.splitlines()
    assert code == 1, out
    assert "ADDED:" not in out and "added_since_build=" not in out
    assert [ln for ln in lines if ln.startswith("NOTE: ")] == [ln for ln in lines if "holds no marker record" in ln]
    assert sum("holds no marker record" in ln for ln in lines) == 1, out
    assert SUMMARY_RE.fullmatch(lines[-1]), out


def test_markers_lint_with_no_manifest_prints_neither_line(tmp_path, capsys, index):
    build = Build(tmp_path, capsys, bodies_set(index, skip={(ORCH_DOCS[0], first_marker(index))}))
    code, out = lint(build)
    assert code == 1, out
    assert "ADDED:" not in out and "NOTE:" not in out


def test_markers_a_task_the_spec_gains_prints_missing_only(tmp_path, capsys):
    short = make_spec()
    short["sprints"][0]["sessions"][1]["tasks"].pop()
    build = Build(tmp_path, capsys, bodies_set(index_of(tmp_path, short)), short)
    code, out = build.run()
    assert code == 0, out
    _write_spec(tmp_path, make_spec())
    code, out = lint(build)
    lines = out.splitlines()
    assert code == 1, out
    assert any(ln.startswith("MISSING: doc=S01-02-02 ") for ln in lines), out
    assert not any(ln.startswith("ADDED: doc=S01-02-02 ") for ln in lines), out
    assert "holds no marker record" not in out


def test_markers_a_section_the_spec_restores_prints_added(tmp_path, capsys):
    omitted = spec_with_omits(task_omits=(SCHEMA_PIN,))
    build = Build(tmp_path, capsys, bodies_set(index_of(tmp_path, omitted)), omitted)
    code, out = build.run()
    assert code == 0, out
    _write_spec(tmp_path, make_spec())
    code, out = lint(build)
    assert code == 1, out
    assert any(ln.startswith(f"ADDED: doc={TASK_DOC} marker=") and ln.endswith(ADDED_TAIL) for ln in out.splitlines()), out
