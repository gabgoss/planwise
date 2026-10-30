"""tools/suite.py: the cached, machine-locked suite runner.

Every test here works on tmp trees and fakes the pytest call. None of them
runs the real suite, so this file costs about a second inside the suite it
guards.
"""

import json
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import ClassVar

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import suite


def _entry(files=(), dirs=()):
    return {"files": set(files), "dirs": set(dirs)}


# ------------------------------------------------------------------ select

class TestSelect:
    TESTS = ("tests/test_a.py", "tests/test_b.py", "tests/test_c.py", "tests/test_new.py")
    DEPS: ClassVar[dict] = {
        "tests/test_a.py": _entry(files={"plugins/planwise/scripts/alpha.py"}),
        "tests/test_b.py": _entry(files={"plugins/planwise/references/one.md"}, dirs={"plugins/planwise/references"}),
        "tests/test_c.py": _entry(files={"plugins/planwise/scripts/gamma.py"}),
    }

    def test_a_file_dependency_selects_its_reader(self):
        assert suite.select(self.TESTS, self.DEPS, {"plugins/planwise/scripts/alpha.py"}, set()) == [
            "tests/test_a.py", "tests/test_new.py"]

    def test_an_unmapped_test_file_is_always_selected(self):
        assert suite.select(self.TESTS, self.DEPS, set(), set()) == ["tests/test_new.py"]

    def test_an_edited_test_file_selects_itself(self):
        assert "tests/test_c.py" in suite.select(self.TESTS, self.DEPS, {"tests/test_c.py"}, set())

    def test_an_added_file_selects_every_test_that_listed_its_folder(self):
        added = "plugins/planwise/references/two.md"
        assert suite.select(self.TESTS, self.DEPS, {added}, {added}) == ["tests/test_b.py", "tests/test_new.py"]

    def test_an_edit_in_a_listed_folder_does_not_select_a_listing_only_test(self):
        deps = {"tests/test_b.py": _entry(dirs={"plugins/planwise/references"})}
        assert suite.select(["tests/test_b.py"], deps, {"plugins/planwise/references/one.md"}, set()) == []


# ------------------------------------------------------- import closure

def test_a_changed_script_pulls_in_its_transitive_importers(tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "leaf.py").write_text("X = 1\n")
    (scripts / "middle.py").write_text("import leaf\n")
    (scripts / "top.py").write_text("from middle import thing\n")
    (scripts / "other.py").write_text("import os\n")
    expanded = suite.expand_with_importers({"s/leaf.py"}, scripts_dir=scripts, scripts_rel="s")
    assert expanded == {"s/leaf.py", "s/middle.py", "s/top.py"}


def test_merge_deps_unions_the_worker_parts(tmp_path):
    (tmp_path / "deps-gw0.json").write_text(json.dumps({"tests/test_a.py": {"files": ["x"], "dirs": []}}))
    (tmp_path / "deps-gw1.json").write_text(json.dumps({"tests/test_a.py": {"files": ["y"], "dirs": ["d"]}}))
    assert suite.merge_deps(tmp_path) == {"tests/test_a.py": {"files": {"x", "y"}, "dirs": {"d"}}}


# ------------------------------------------------------------- fingerprint

def _git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


@pytest.fixture
def tiny_repo(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / ".gitignore").write_text("ignored.txt\n")
    (repo / "a.py").write_text("A = 1\n")
    _git(repo, "add", "-A")
    monkeypatch.setattr(suite, "REPO", repo)
    monkeypatch.setattr(suite, "OUTER", None)
    return repo


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
class TestFingerprint:
    def test_stable_when_nothing_changes(self, tiny_repo):
        assert suite.fingerprint() == suite.fingerprint()

    def test_a_tracked_edit_changes_it(self, tiny_repo):
        before = suite.fingerprint()
        (tiny_repo / "a.py").write_text("A = 2\n")
        assert suite.fingerprint() != before

    def test_an_untracked_file_changes_it(self, tiny_repo):
        before = suite.fingerprint()
        (tiny_repo / "b.py").write_text("")
        assert suite.fingerprint() != before

    def test_an_ignored_file_does_not(self, tiny_repo):
        before = suite.fingerprint()
        (tiny_repo / "ignored.txt").write_text("noise")
        assert suite.fingerprint() == before


# -------------------------------------------------------- cache and lock

@pytest.fixture
def fake_run(tmp_path, monkeypatch):
    """main() --full against a tmp cache, with pytest and the fingerprint faked."""
    monkeypatch.setattr(suite, "CACHE", tmp_path / "cache")
    monkeypatch.setattr(suite, "_test_files", lambda: ["tests/test_a.py"])
    state = {"fingerprints": [], "runs": 0}

    def fingerprint():
        return state["fingerprints"].pop(0) if state["fingerprints"] else "f" * 64

    def run_pytest(targets, workers, record_deps, label):
        state["runs"] += 1
        return {"returncode": 0, "summary": "1 passed in 0.01s", "failed": [], "duration_s": 0.0, "log": "x"}

    monkeypatch.setattr(suite, "fingerprint", fingerprint)
    monkeypatch.setattr(suite, "run_pytest", run_pytest)
    return state


def test_a_second_call_on_the_same_tree_reads_the_cache(fake_run, capsys):
    assert suite.main(["--full"]) == 0
    assert suite.main(["--full"]) == 0
    assert fake_run["runs"] == 1
    assert "cached result for this tree" in capsys.readouterr().out


def test_a_tree_edited_mid_run_is_not_stored(fake_run, capsys):
    fake_run["fingerprints"] = ["a" * 64, "b" * 64, "a" * 64, "a" * 64]
    suite.main(["--full"])
    assert "NOT stored" in capsys.readouterr().out
    suite.main(["--full"])
    assert fake_run["runs"] == 2


def test_no_cache_forces_a_run(fake_run):
    suite.main(["--full"])
    suite.main(["--full", "--no-cache"])
    assert fake_run["runs"] == 2


def test_a_held_lock_past_the_wait_budget_exits_busy(fake_run, tmp_path):
    holder = suite.MachineLock(tmp_path / "cache" / "run.lock")
    assert holder.try_acquire()
    try:
        assert suite.main(["--full", "--wait", "0"]) == suite.EXIT_BUSY
    finally:
        holder.release()
    assert fake_run["runs"] == 0


def test_a_waiter_reads_the_result_the_holder_stored(fake_run, tmp_path):
    holder = suite.MachineLock(tmp_path / "cache" / "run.lock")
    assert holder.try_acquire()
    out = {}
    waiter = threading.Thread(target=lambda: out.setdefault("code", suite.main(["--full", "--wait", "30"])))
    waiter.start()
    time.sleep(0.5)
    suite.store_result("f" * 64 + "-full", {
        "returncode": 1, "summary": "1 failed in 0.01s", "failed": ["tests/test_a.py::t"],
        "duration_s": 0.0, "log": "x"})
    holder.release()
    waiter.join(30)
    assert out["code"] == 1
    assert fake_run["runs"] == 0


def test_a_full_result_answers_a_changed_run_by_its_own_files(fake_run, monkeypatch):
    monkeypatch.setattr(suite, "plan_changed", lambda since: (["tests/test_b.py"], "1 changed path(s)"))
    suite.store_result("f" * 64 + "-full", {
        "returncode": 1, "summary": "1 failed in 0.01s", "failed": ["tests/test_a.py::t"],
        "duration_s": 0.0, "log": "x"})
    assert suite.main([]) == 0
    assert fake_run["runs"] == 0


@pytest.mark.parametrize(("have_xdist", "expect_n"), [(True, True), (False, False)])
def test_workers_are_requested_only_when_xdist_is_installed(tmp_path, monkeypatch, have_xdist, expect_n):
    monkeypatch.setattr(suite, "CACHE", tmp_path / "cache")
    monkeypatch.setattr(suite, "_have_xdist", lambda: have_xdist)
    seen = {}

    def fake_subprocess_run(cmd, **kwargs):
        seen["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(suite.subprocess, "run", fake_subprocess_run)
    suite.run_pytest(["tests"], workers=4, record_deps=False, label="full")
    assert ("-n" in seen["cmd"]) is expect_n


def test_a_harness_change_escalates_to_the_full_suite(monkeypatch):
    monkeypatch.setattr(suite, "load_deps", dict)
    monkeypatch.setattr(suite, "changed_paths", lambda since: ({"tests/conftest.py"}, set()))
    targets, reason = suite.plan_changed("HEAD")
    assert targets is None and "tests/conftest.py" in reason


def test_no_map_escalates_to_the_full_suite(monkeypatch):
    monkeypatch.setattr(suite, "load_deps", lambda: None)
    assert suite.plan_changed("HEAD") == (None, "no dependency map yet")
