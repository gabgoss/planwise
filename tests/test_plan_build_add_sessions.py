"""Tests for the `add-sessions` command of scripts/plan_build.py.

The built plan comes from a real `build` of a one-session spec. The added session is the
second session of the sample spec, with its bodies file from the same bodies producer.
"""

import json
import re
import sys
from pathlib import Path

import pytest

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import plan_add_sessions
import plan_build as pb
from test_plan_build import (
    GATE_LINE_RE,
    META,
    Build,
    bodies_set,
    index_of,
    make_spec,
    meta_build,
    meta_spec,
)

MASTER = "QZX-Master-Plan.md"
SPRINT = "Sprint-01-LedgerCore/QZX-S01-Sprint-Plan.md"
NEW_FOLDER = "Sprint-01-LedgerCore/Session-02-WritePath"
NEW_BODIES = "QZX-bodies-S01-02.md"
HAND_EDIT = b"\nA line the author added by hand.\n"


def one_session_spec():
    spec = make_spec()
    spec["sprints"][0]["sessions"] = spec["sprints"][0]["sessions"][:1]
    return spec


class Grown:
    """A built one-session plan, a hand edit in two plan files, and a spec that gained a second session."""

    def __init__(self, tmp_path, capsys):
        every = bodies_set(index_of(tmp_path, make_spec()))
        first = {name: text for name, text in every.items() if name != NEW_BODIES}
        first["QZX-bodies-plan.md"] = bodies_set(index_of(tmp_path, one_session_spec()))["QZX-bodies-plan.md"]
        self.build = Build(tmp_path, capsys, first, one_session_spec())
        code, out = self.build.run()
        assert code in (0, 1), out
        self.edited = {}
        for rel in (SPRINT, MASTER):
            target = self.build.out / rel
            target.write_bytes(target.read_bytes() + HAND_EDIT)
            self.edited[rel] = target.read_bytes()
        self.build.spec.write_text(json.dumps(make_spec()), encoding="utf-8")
        (self.build.bodies / "QZX-bodies-plan.md").write_bytes(every["QZX-bodies-plan.md"].encode("utf-8"))
        (self.build.bodies / NEW_BODIES).write_bytes(every[NEW_BODIES].encode("utf-8"))

    def argv(self, *sessions):
        flags = [part for s in sessions for part in ("--session", s)]
        return ["add-sessions", "--spec", str(self.build.spec), "--bodies-dir", str(self.build.bodies),
                "--out", str(self.build.out), "--config", str(self.build.config), "--skip-index", *flags]

    def run(self, *sessions):
        code = pb.main(self.argv(*sessions))
        return code, self.build.capsys.readouterr().out

    def tree(self):
        return {p.relative_to(self.build.out).as_posix(): p.read_bytes()
                for p in self.build.out.rglob("*") if p.is_file()}

    def manifest(self):
        return json.loads(self.build.manifest.read_text(encoding="utf-8"))["files"]


@pytest.fixture
def grown(tmp_path, capsys):
    return Grown(tmp_path, capsys)


def test_add_sessions_writes_the_new_session_and_changes_no_existing_file(grown):
    before, hashes = grown.tree(), grown.manifest()
    code, out = grown.run("S01-02")
    assert code in (0, 1), out
    after = grown.tree()
    added = sorted(set(after) - set(before))
    assert added and all(rel.startswith(f"{NEW_FOLDER}/") for rel in added), added
    assert f"{NEW_FOLDER}/Outputs/.gitkeep" in added
    assert {rel: after[rel] for rel in before} == before
    assert {rel: after[rel] for rel in grown.edited} == grown.edited
    assert f"added {len(added)} files to " in out
    assert [name for name, *_ in GATE_LINE_RE.findall(out)] == list(pb.GATES)
    assert re.search(r"^outside=\d+$", out, re.MULTILINE), out
    assert set(grown.manifest()) == set(hashes) | set(added)


def test_add_sessions_prints_the_plan_rows(grown):
    _code, out = grown.run("S01-02")
    rows = [line for line in out.splitlines() if line.startswith("ADD-ROW: ")]
    assert any(line.startswith(f"ADD-ROW: {SPRINT}: | 2 | QZX-S01-02 | WritePath |") for line in rows), rows
    assert any(line.startswith(f"ADD-ROW: {SPRINT}: ### Session 02: WritePath (QZX-S01-02)") for line in rows), rows
    assert any(line.startswith(f"ADD-ROW: {MASTER}: | Sprint-01 | Session-02-WritePath |") for line in rows), rows
    assert not any("S01-01" in line or "Session-01-" in line for line in rows), rows
    assert "SESSIONS: sprint=2 plan=2" in out.splitlines()


def test_a_later_build_still_sees_the_hand_edits(grown):
    hashes = grown.manifest()
    grown.run("S01-02")
    assert {rel: grown.manifest()[rel] for rel in hashes} == hashes
    code, out = grown.build.run()
    assert code == 2, out
    changed = [line.removeprefix("CHANGED: ") for line in out.splitlines() if line.startswith("CHANGED: ")]
    assert sorted(changed) == sorted(grown.edited), out


def test_an_existing_file_a_gate_rewrites_gets_its_bytes_put_back(grown, tmp_path):
    source = tmp_path / "src" / "orchard" / "parse.py"  # a Write-Set row of the built Sprint Plan, now on disk
    source.parent.mkdir(parents=True)
    source.write_bytes(b"x = 1\n" * 900)
    _code, out = grown.run("S01-02")
    assert f"KEPT: {SPRINT}: " in out, out
    assert {rel: grown.tree()[rel] for rel in grown.edited} == grown.edited


def test_a_meta_plan_adds_under_its_meta_folder(tmp_path, capsys):
    full = meta_spec()
    one = meta_spec()
    one["sprints"][0]["sessions"] = one["sprints"][0]["sessions"][:1]
    every = bodies_set(index_of(tmp_path, full))
    first = dict(every)
    del first[NEW_BODIES]
    first["QZX-bodies-plan.md"] = bodies_set(index_of(tmp_path, one))["QZX-bodies-plan.md"]
    build = meta_build(tmp_path, capsys, one, first)
    code, out = build.run()
    assert code in (0, 1), out
    before = {p: p.read_bytes() for p in build.root.rglob("*") if p.is_file()}
    build.spec.write_text(json.dumps(full), encoding="utf-8")
    for name, text in every.items():
        (build.bodies / name.replace("QZX-", f"{META}-")).write_bytes(text.encode("utf-8"))
    code = pb.main(["add-sessions", "--spec", str(build.spec), "--bodies-dir", str(build.bodies), "--out",
                    str(build.out), "--config", str(build.config), "--skip-index", "--session", "S01-02"])
    out = capsys.readouterr().out
    assert code in (0, 1), out
    assert {p: p.read_bytes() for p in before} == before
    assert list((build.root / "Sprint-01-X" / "Session-02-WritePath").glob(f"{META}-S01-02-01-*.md"))
    assert f"ADD-ROW: {META}-META-Master-Plan.md: | Sprint-01 | Session-02-WritePath |" in out, out


def test_the_new_sessions_detail_block_is_printed_whole(grown):
    _code, out = grown.run("S01-02")
    block = [line.removeprefix(f"BLOCK: {SPRINT}: ") for line in out.splitlines() if line.startswith("BLOCK: ")]
    assert block[0] == "### Session 02: WritePath (QZX-S01-02)", block
    assert "**Objective:** Write the ledger" in block
    assert any(line.startswith("| 2 | VerifyRows") for line in block), block
    assert "**Key Requirements:**" in block
    assert not any("Session 01" in line or line == "---" for line in block), block


def test_a_session_the_plan_holds_under_another_name_is_refused(grown):
    grown.run("S01-02")
    spec = make_spec()
    spec["sprints"][0]["sessions"][1]["name"] = "StorePath"
    grown.build.spec.write_text(json.dumps(spec), encoding="utf-8")
    before = grown.tree()
    code, out = grown.run("S01-02")
    assert code == 2, out
    assert "REFUSED: session S01-02 is already in the plan under " in out, out
    assert grown.tree() == before


def test_a_spec_that_renames_a_built_session_is_refused(grown):
    spec = make_spec()
    spec["sprints"][0]["sessions"][0]["name"] = "LoadPath"
    grown.build.spec.write_text(json.dumps(spec), encoding="utf-8")
    before = grown.tree()
    code, out = grown.run("S01-02")
    assert code == 2, out
    assert "MOVED: Sprint-01-LedgerCore/Session-01-ReadPath/QZX-S01-01-Orchestration.md" in out.splitlines()
    assert "REFUSED: the spec renames, renumbers or drops 1 built session(s). Fix: " in out
    assert grown.tree() == before


def test_a_lint_error_in_the_plan_bodies_refuses(grown):
    path = grown.build.bodies / "QZX-bodies-plan.md"
    path.write_bytes(path.read_bytes() + b"\n<!-- doc: S09 -->\n\n<!-- fill: Nothing -->\n\nText.\n")
    before = grown.tree()
    code, out = grown.run("S01-02")
    assert code == 2, out
    assert "LINT: doc=S09 " in out and "REFUSED: " in out, out
    assert grown.tree() == before


def test_a_printed_row_with_no_body_is_reported(grown):
    path = grown.build.bodies / "QZX-bodies-plan.md"
    text = path.read_text(encoding="utf-8").replace("<!-- fill: Requirement 1", "<!-- fill: Requirement 1 [1]")
    path.write_bytes(text.encode("utf-8"))  # only the first block keeps its body, so the new block holds the marker
    code, out = grown.run("S01-02")
    assert code == 1, out
    assert "NOTE: 1 printed line(s) still hold a FILL marker." in out, out


def test_a_cited_warn_file_keeps_the_scan_finding(grown, tmp_path):
    grown.build.config.write_text("plans: plans\ncontext:\n  token_saver: true\n", encoding="utf-8")  # scan on
    cited = tmp_path / "src" / "orchard" / "ledger.py"  # the Required Context of every task
    cited.parent.mkdir(parents=True)
    cited.write_bytes(b"x = 1  # a line of the ledger\n" * 6000)
    code, out = grown.run("S01-02")
    assert code == 1, out
    assert re.search(r"^gate=scan status=finding ", out, re.MULTILINE), out


def test_a_manifest_with_no_marker_record_gains_none(grown):
    data = json.loads(grown.build.manifest.read_text(encoding="utf-8"))
    del data["markers"]
    grown.build.manifest.write_text(json.dumps(data), encoding="utf-8")
    _code, out = grown.run("S01-02")
    assert "markers" not in json.loads(grown.build.manifest.read_text(encoding="utf-8")), out


def test_the_gate_lines_that_name_no_new_file_are_counted_unless_the_gate_could_not_run():
    files = ["a/b/QZX-S01-02-01-Sonnet-WriteRows.md"]
    report = [
        ("estimates", "finding", "failed=1", ["session=S01-02 exit=0: ERROR: no config",
                                              "session=S01-02 exit=0: Sprint Plan: session row"]),
        ("deviations", "finding", "A=0 B=0 C=0", ["cannot grade the tree: PlanReadError: bad bytes"]),
        ("headings", "finding", "h2=1 stray=1", ["old/File.md: ## Extra"]),
        ("scan", "finding", "exit=1", ["src/orchard/ledger.py  (Warn/size)"]),
    ]
    kept, outside = plan_add_sessions.only_new(report, files)
    assert outside == 2
    assert [(name, status, len(details)) for name, status, _figures, details in kept] == [
        ("estimates", "finding", 1), ("deviations", "finding", 1), ("headings", "ok", 0), ("scan", "finding", 1)]


def test_a_second_run_refuses_with_exists_and_writes_nothing(grown):
    grown.run("S01-02")
    before, manifest = grown.tree(), grown.build.manifest.read_bytes()
    code, out = grown.run("S01-02")
    assert code == 2
    assert f"EXISTS: {NEW_FOLDER}/Outputs/.gitkeep" in out.splitlines()
    assert "REFUSED: " in out and " Fix: " in out
    assert (grown.tree(), grown.build.manifest.read_bytes()) == (before, manifest)


def test_an_unknown_session_is_refused(grown):
    before = grown.tree()
    code, out = grown.run("S01-02", "S01-09")
    assert code == 2
    assert "REFUSED: session S01-09 is not in the spec. Fix: " in out
    assert grown.tree() == before


def test_a_missing_session_flag_is_refused(grown, capsys):
    with pytest.raises(SystemExit) as caught:
        pb.main(grown.argv())
    assert caught.value.code == 2
    assert "--session" in capsys.readouterr().err


def test_a_folder_no_build_wrote_is_refused(grown, tmp_path):
    empty = tmp_path / "Exec-Empty"
    empty.mkdir()
    grown.build.out = empty
    code, out = grown.run("S01-02")
    assert code == 2
    assert "holds no file that QZX-build-manifest.json lists. Fix: " in out
    assert list(empty.iterdir()) == []
