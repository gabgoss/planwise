"""Tests for the build manifest and the part-way write failure of scripts/plan_build.py.

Shared helpers live in `tests/test_plan_build.py`.
"""

import hashlib
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
    MANIFEST,
    TEMPLATES,
    Build,
    _write_spec,
    bodies_set,
    index_of,
    make_spec,
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
