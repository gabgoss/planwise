#!/usr/bin/env python3
"""Run the plugin test suite once per tree state, one run at a time per machine.

Dev-repo tool. This is the one entry point for running this repo's tests from a
Claude Code session or a script.

A suite result is a function of the tree, so the runner:

- fingerprints the tree (every tracked and untracked, non-ignored file of this
  repo, the authoring project's CLAUDE.md and .claude/rules/ when this repo is
  nested in one, and the Python, pytest and xdist versions)
- returns a stored result when one exists for that fingerprint
- holds a machine-wide lock while pytest runs, so concurrent sessions queue
  instead of each loading the suite into memory. A waiting caller re-reads the
  cache when it gets the lock, because the run it waited on usually stored the
  answer
- runs pytest in parallel with pytest-xdist (`--dist loadfile`, so a file's
  tests stay in one worker and keep their order)
- stores a result only when the fingerprint after the run equals the one before
  it. A tree edited mid-run is reported but never cached

Modes:
    --changed (default)  only the test files the working-tree change affects
    --full               every test file. Also records the dependency map that
                         --changed selects from (tools/suite_deps.py) when the
                         map is missing or older than 12 hours, or when
                         --record-deps is given. Recording costs about 18% of
                         a full run (258 s against 219 s, 4 workers, 2026-10-22)

Workers: 4 by default. Measured 2026-10-22 on a 12-core, 7.8 GB machine, a full
run took 219-258 s at 4 workers with a peak of 530-600 MiB for the whole process
tree, and 220 s at 6 workers with 860 MiB. The default keeps memory low for a
machine that runs several sessions at once.

--changed selects a test file when it changed, when the map has no entry for it
(a new file), when it depends on a changed file, or when it listed a folder in
which a file was added or deleted. A changed script also counts every script
that imports it, directly or through other scripts, because a subprocess runs
code the map cannot see. --changed escalates to --full when the change touches
the test harness itself (conftest.py, pytest.ini, this runner) or no map exists.
--changed is a per-task gate. --full stays the gate before a commit: the map
misses a test that only reads a module-level constant another file imported.

Exit codes: pytest's own (0 pass, 1 failures, 2+ errors), 0 when --changed
selects nothing, and 75 when another run held the lock past --wait seconds.

Usage, from anywhere (the runner locates the repo from its own path):
    python -B tools/suite.py                  # affected tests only
    python -B tools/suite.py --full           # whole suite
    python -B tools/suite.py --list           # print the --changed selection, run nothing
    python -B tools/suite.py --full --no-cache
    python -B tools/suite.py --since <rev>    # changes since <rev>, not since HEAD
"""

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOLS = REPO / "tools"
TESTS = REPO / "tests"
SCRIPTS_REL = "plugins/planwise/scripts"
CACHE = REPO / ".pytest_cache" / "planwise-suite"
DEPS = CACHE / "deps.json"
OUTER = REPO.parent.parent if REPO.parent.name == "cloned-repos" else None

# A change to any of these changes how every test runs, so --changed runs everything.
HARNESS = frozenset({"conftest.py", "tests/conftest.py", "pytest.ini", "tools/suite.py", "tools/suite_deps.py"})

DEFAULT_WORKERS = 4
DEFAULT_WAIT = 300
DEPS_MAX_AGE_S = 12 * 3600
EXIT_BUSY = 75
KEEP_RESULTS = 200

_SUMMARY = re.compile(r"\b(passed|failed|error|errors|skipped|deselected|no tests ran)\b.* in [\d.]+s")
_FAILED = re.compile(r"^(FAILED|ERROR) (\S+)")


# --------------------------------------------------------------------- git

def _git(root, *args):
    out = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, check=True
    ).stdout
    return out.decode("utf-8", "surrogateescape")


def _outer_extras():
    """The authoring project's files that tests read: CLAUDE.md and .claude/rules/."""
    if OUTER is None:
        return []
    paths = [OUTER / "CLAUDE.md"]
    rules = OUTER / ".claude" / "rules"
    if rules.is_dir():
        paths.extend(sorted(p for p in rules.rglob("*") if p.is_file()))
    return [p for p in paths if p.is_file()]


def _rel(path):
    return os.path.relpath(path, REPO).replace(os.sep, "/")


# ------------------------------------------------------------- fingerprint

def fingerprint():
    """SHA-256 over every input that can change a test result."""
    h = hashlib.sha256()
    try:
        import pytest
        import xdist
        versions = f"{sys.version}|{pytest.__version__}|{xdist.__version__}"
    except ImportError as exc:
        versions = f"{sys.version}|{exc}"
    h.update(versions.encode())
    names = sorted(set(filter(None, _git(REPO, "ls-files", "-co", "--exclude-standard", "-z").split("\0"))))
    files = [(name, REPO / name) for name in names]
    files += [(_rel(p), p) for p in _outer_extras()]
    for name, path in files:
        h.update(name.encode("utf-8", "surrogateescape") + b"\0")
        try:
            h.update(hashlib.sha256(path.read_bytes()).digest())
        except (FileNotFoundError, IsADirectoryError, PermissionError):
            h.update(b"<absent>")
    return h.hexdigest()


# ------------------------------------------------------------------- cache

def _result_path(key):
    return CACHE / f"result-{key}.json"


def load_result(key):
    try:
        return json.loads(_result_path(key).read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return None


def store_result(key, result):
    CACHE.mkdir(parents=True, exist_ok=True)
    tmp = _result_path(key).with_suffix(".tmp")
    tmp.write_text(json.dumps(result, indent=1), encoding="utf-8")
    os.replace(tmp, _result_path(key))
    old = sorted(CACHE.glob("result-*.json"), key=lambda p: p.stat().st_mtime)
    for path in old[:-KEEP_RESULTS]:
        path.unlink(missing_ok=True)


# -------------------------------------------------------------------- lock

class MachineLock:
    """An OS file lock on <cache>/run.lock. The OS drops it when the holder dies."""

    def __init__(self, path):
        self.path = path
        self.handle = None

    def try_acquire(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(self.path, "a+b")  # noqa: SIM115 - held open for the lock's lifetime
        try:
            if os.name == "nt":
                import msvcrt
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            return False
        self.handle = handle
        return True

    def release(self):
        if self.handle is None:
            return
        try:
            if os.name == "nt":
                import msvcrt
                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        finally:
            self.handle.close()
            self.handle = None


def _holder_path():
    return CACHE / "run.holder.json"


def _describe_holder():
    try:
        info = json.loads(_holder_path().read_text(encoding="utf-8"))
        return f"pid {info.get('pid')}, {info.get('mode')} run, started {info.get('started')}"
    except (FileNotFoundError, ValueError):
        return "unknown holder"


# --------------------------------------------------------------- selection

def changed_paths(since):
    """(changed, added_or_deleted) as repo-relative paths, against `since`."""
    changed, structural = set(), set()
    for line in _git(REPO, "diff", "--name-status", "--no-renames", since).splitlines():
        status, _, path = line.partition("\t")
        changed.add(path)
        if status[:1] in ("A", "D"):
            structural.add(path)
    for path in filter(None, _git(REPO, "ls-files", "-o", "--exclude-standard", "-z").split("\0")):
        changed.add(path)
        structural.add(path)
    if OUTER is not None:
        scope = ["CLAUDE.md", ".claude/rules"]
        for line in _git(OUTER, "diff", "--name-status", "--no-renames", "HEAD", "--", *scope).splitlines():
            status, _, path = line.partition("\t")
            rel = _rel(OUTER / path)
            changed.add(rel)
            if status[:1] in ("A", "D"):
                structural.add(rel)
        for path in filter(None, _git(OUTER, "ls-files", "-o", "--exclude-standard", "-z", "--", *scope).split("\0")):
            rel = _rel(OUTER / path)
            changed.add(rel)
            structural.add(rel)
    return changed, structural


def script_importers(scripts_dir):
    """module -> the set of script modules that import it directly."""
    stems = {p.stem for p in scripts_dir.glob("*.py")}
    importers = {stem: set() for stem in stems}
    for path in scripts_dir.glob("*.py"):
        try:
            tree = ast.parse(path.read_bytes())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module.split(".")[0]]
            else:
                continue
            for name in names:
                if name in importers and name != path.stem:
                    importers[name].add(path.stem)
    return importers


def expand_with_importers(changed, scripts_dir=None, scripts_rel=SCRIPTS_REL):
    """Add every script that transitively imports a changed script."""
    scripts_dir = scripts_dir or REPO / scripts_rel
    importers = script_importers(scripts_dir)
    prefix = scripts_rel + "/"
    todo = [p[len(prefix):-3] for p in changed if p.startswith(prefix) and p.endswith(".py") and "/" not in p[len(prefix):]]
    seen = set(todo)
    while todo:
        for parent in importers.get(todo.pop(), ()):
            if parent not in seen:
                seen.add(parent)
                todo.append(parent)
    return set(changed) | {f"{prefix}{stem}.py" for stem in seen}


def _ancestors(path):
    parts = path.split("/")[:-1]
    return {"/".join(parts[:i]) for i in range(1, len(parts) + 1)}


def select(test_files, deps, changed, structural):
    """The test files a change affects. `deps` is the merged map from a full run."""
    walked_targets = set()
    for path in structural:
        walked_targets |= _ancestors(path)
    selected = []
    for test in test_files:
        entry = deps.get(test)
        if (
            test in changed
            or entry is None
            or changed.intersection(entry["files"])
            or walked_targets.intersection(entry["dirs"])
        ):
            selected.append(test)
    return selected


def merge_deps(parts_dir):
    merged = {}
    for part in sorted(parts_dir.glob("deps-*.json")):
        for test, entry in json.loads(part.read_text(encoding="utf-8")).items():
            slot = merged.setdefault(test, {"files": set(), "dirs": set()})
            slot["files"].update(entry["files"])
            slot["dirs"].update(entry["dirs"])
    return merged


def _deps_stale():
    try:
        return time.time() - DEPS.stat().st_mtime > DEPS_MAX_AGE_S
    except FileNotFoundError:
        return True


def load_deps():
    try:
        raw = json.loads(DEPS.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return None
    return {t: {"files": set(e["files"]), "dirs": set(e["dirs"])} for t, e in raw.items()}


# --------------------------------------------------------------------- run

def run_pytest(targets, workers, record_deps, label):
    CACHE.mkdir(parents=True, exist_ok=True)
    log = CACHE / f"last-{label}.log"
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    cmd = [sys.executable, "-B", "-m", "pytest", "-q", "-rfE", "-c", str(REPO / "pytest.ini")]
    if workers >= 2:
        cmd += ["-n", str(workers), "--dist", "loadfile"]
    parts_dir = CACHE / "deps-parts"
    if record_deps:
        parts_dir.mkdir(exist_ok=True)
        for old in parts_dir.glob("deps-*.json"):
            old.unlink()
        env["SUITE_DEPS_DIR"] = str(parts_dir)
        env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(TOOLS), env.get("PYTHONPATH")]))
        cmd += ["-p", "suite_deps"]
    cmd += targets
    start = time.monotonic()
    with open(log, "wb") as out:
        code = subprocess.run(cmd, cwd=REPO, env=env, stdout=out, stderr=subprocess.STDOUT, check=False).returncode
    duration = round(time.monotonic() - start, 1)
    text = log.read_text(encoding="utf-8", errors="replace")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    summary = next((line.strip("= ") for line in reversed(lines) if _SUMMARY.search(line)), f"pytest exit {code}, no summary line")
    failed = sorted({m.group(2) for m in map(_FAILED.match, lines) if m})
    if record_deps and code in (0, 1):
        merged = merge_deps(parts_dir)
        if merged:
            payload = {t: {"files": sorted(e["files"]), "dirs": sorted(e["dirs"])} for t, e in sorted(merged.items())}
            DEPS.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return {"returncode": code, "summary": summary, "failed": failed, "duration_s": duration, "log": str(log)}


def _report(mode, fp, result, note):
    print(f"suite {mode}: {result['summary']}")
    print(f"  tree {fp[:12]} | {note} | {result['duration_s']} s | log {result['log']}")
    for node in result["failed"]:
        print(f"  FAILED {node}")


# -------------------------------------------------------------------- main

def _test_files():
    return sorted(_rel(p) for p in TESTS.glob("test_*.py"))


def plan_changed(since):
    """(targets, reason). targets None means escalate to the full suite."""
    deps = load_deps()
    if deps is None:
        return None, "no dependency map yet"
    changed, structural = changed_paths(since)
    hit = sorted(changed & HARNESS)
    if hit:
        return None, f"harness changed: {', '.join(hit)}"
    expanded = expand_with_importers(changed)
    return select(_test_files(), deps, expanded, structural), f"{len(changed)} changed path(s)"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--full", action="store_true", help="run every test file")
    mode.add_argument("--changed", action="store_true", help="run only affected test files (default)")
    parser.add_argument("--list", action="store_true", help="print the --changed selection and exit")
    parser.add_argument("--since", default="HEAD", help="git revision the change is measured from (default HEAD)")
    parser.add_argument("--no-cache", action="store_true", help="ignore a stored result and run")
    parser.add_argument("--record-deps", action="store_true", help="refresh the dependency map on this full run")
    parser.add_argument("-n", "--workers", type=int, default=DEFAULT_WORKERS, help=f"xdist workers (default {DEFAULT_WORKERS})")
    parser.add_argument("--wait", type=int, default=DEFAULT_WAIT, help=f"seconds to wait for another run's lock (default {DEFAULT_WAIT})")
    args = parser.parse_args(argv)

    full = args.full
    targets, reason = (None, "requested") if full else plan_changed(args.since)
    if targets is None:
        full = True
    if args.list:
        print(f"full suite ({reason})" if full else f"{len(targets)} test file(s) ({reason})")
        for test in targets or ():
            print(f"  {test}")
        return 0
    if not full and not targets:
        print(f"suite changed: no affected test files ({reason})")
        return 0

    fp = fingerprint()
    mode_name = "full" if full else "changed"
    key_full = f"{fp}-full"
    key = key_full if full else f"{fp}-changed-{hashlib.sha256(chr(0).join(targets).encode()).hexdigest()[:16]}"

    def cached():
        if args.no_cache:
            return None
        hit = load_result(key)
        if hit is None and not full:
            whole = load_result(key_full)
            if whole is not None:
                # A full result for this tree answers any subset of it.
                mine = [n for n in whole["failed"] if n.split("::")[0] in targets]
                hit = dict(whole, failed=mine, returncode=1 if mine else 0 if whole["returncode"] in (0, 1) else whole["returncode"])
        return hit

    hit = cached()
    if hit is not None:
        _report(mode_name, fp, hit, "cached result for this tree")
        return hit["returncode"]

    lock = MachineLock(CACHE / "run.lock")
    deadline = time.monotonic() + args.wait
    announced = False
    while not lock.try_acquire():
        if not announced:
            print(f"waiting for another suite run ({_describe_holder()})", flush=True)
            announced = True
        if time.monotonic() >= deadline:
            print(f"suite {mode_name}: another run still holds the lock after {args.wait} s. "
                  "Re-run this command later; a finished run's result is read from the cache.")
            return EXIT_BUSY
        time.sleep(2)
    try:
        hit = cached()
        if hit is not None:
            _report(mode_name, fp, hit, "result stored by the run this call waited for")
            return hit["returncode"]
        _holder_path().write_text(json.dumps({
            "pid": os.getpid(), "mode": mode_name, "started": time.strftime("%Y-%m-%d %H:%M:%S"),
        }), encoding="utf-8")
        run_targets = [str(TESTS)] if full else [str(REPO / t) for t in targets]
        workers = args.workers if full else min(args.workers, len(targets) // 4)
        result = run_pytest(run_targets, workers, record_deps=full and (args.record_deps or _deps_stale()), label=mode_name)
        result["files"] = len(_test_files()) if full else len(targets)
        after = fingerprint()
        if after == fp:
            store_result(key, result)
            note = f"{result['files']} file(s), {reason}, stored"
        else:
            note = f"{result['files']} file(s), {reason}, NOT stored: the tree changed during the run"
        _report(mode_name, fp, result, note)
        return result["returncode"]
    finally:
        _holder_path().unlink(missing_ok=True)
        lock.release()


if __name__ == "__main__":
    sys.exit(main())
