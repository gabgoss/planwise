"""pytest plugin: record which repo files each test file depends on.

Dev-repo tool, loaded only by tools/suite.py (`-p suite_deps`) on a full run.
It writes one JSON map per process, which suite.py merges into the dependency
map that `suite.py --changed` selects from.

For each test file (tests/<name>.py) it records three kinds of dependency:

- "files": repo files whose Python code ran while that file's tests were
  collected or run (sys.monitoring PY_START, so code reached through a
  conftest helper counts), plus repo files the tests opened (audit event
  `open`), plus repo paths named in a subprocess argv (audit event
  `subprocess.Popen`), because a child process runs code this process cannot see.
- "dirs": repo folders the tests listed (audit events `os.scandir` and
  `os.listdir`, which cover Path.rglob, glob and os.walk). Adding or deleting
  a file in such a folder selects the test file.

Paths are stored relative to the plugin repo root with forward slashes. A path
in the authoring project that contains this repo keeps its `../` prefix.
Anything outside both roots (tmp dirs, site-packages) is dropped.

Output: <cache dir>/deps-<worker id>.json, where the cache dir comes from the
SUITE_DEPS_DIR environment variable. With the variable unset the plugin does
nothing, so a stray `-p suite_deps` costs nothing.
"""

import json
import os
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
_ROOTS = [str(REPO)]
if REPO.parent.name == "cloned-repos":
    _ROOTS.append(str(REPO.parent.parent))
_ROOTS = [os.path.normcase(r) + os.sep for r in _ROOTS]
_REPO_PREFIX = os.path.normcase(str(REPO))

_OUT_DIR = os.environ.get("SUITE_DEPS_DIR")
_EVENTS = frozenset({"open", "os.scandir", "os.listdir", "subprocess.Popen"})
_SCRIPTS_REL = "plugins/planwise/scripts"
_SCRIPT_STEMS = frozenset(p.stem for p in (REPO / _SCRIPTS_REL).glob("*.py"))
_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

_current = None  # repo-relative path of the test file being collected or run
_deps: dict = {}  # test file -> {"files": set, "dirs": set}
_rel_cache: dict = {}


def _rel(path):
    """Repo-relative forward-slash path, or None when outside both roots."""
    try:
        raw = os.fspath(path)
    except TypeError:
        return None
    if isinstance(raw, bytes):
        try:
            raw = os.fsdecode(raw)
        except (UnicodeDecodeError, ValueError):
            return None
    hit = _rel_cache.get(raw)
    if hit is not None or raw in _rel_cache:
        return hit
    result = None
    try:
        absolute = os.path.normcase(os.path.abspath(raw))
    except (ValueError, OSError):
        absolute = ""
    if absolute and any(absolute.startswith(r) or absolute + os.sep == r for r in _ROOTS):
        result = os.path.relpath(absolute, _REPO_PREFIX).replace(os.sep, "/")
        if "/.pytest_cache/" in "/" + result + "/" or "__pycache__" in result:
            result = None
    _rel_cache[raw] = result
    return result


def _bucket():
    entry = _deps.get(_current)
    if entry is None:
        entry = _deps[_current] = {"files": set(), "dirs": set()}
    return entry


def _audit(event, args):
    if _current is None or event not in _EVENTS:
        return
    if event == "open":
        rel = _rel(args[0]) if args and not isinstance(args[0], int) else None
        if rel:
            _bucket()["files"].add(rel)
    elif event == "subprocess.Popen":
        argv = args[1] if len(args) > 1 else None
        if isinstance(argv, (str, bytes, os.PathLike)):
            argv = [argv]
        for item in argv or ():
            rel = _rel(item)
            if rel and os.path.isfile(item):
                _bucket()["files"].add(rel)
            elif isinstance(item, str):
                # `python -c "import <module>"` names a script by module, not by path.
                for word in _WORD.findall(item):
                    if word in _SCRIPT_STEMS:
                        _bucket()["files"].add(f"{_SCRIPTS_REL}/{word}.py")
    else:
        target = args[0] if args else None
        rel = _rel(target if target is not None else ".")
        if rel:
            _bucket()["dirs"].add(rel)


def _on_start(code, offset):
    if _current is not None:
        rel = _rel(code.co_filename)
        if rel:
            _bucket()["files"].add(rel)
    return sys.monitoring.DISABLE


def _claim_tool_id():
    mon = getattr(sys, "monitoring", None)
    if mon is None:
        return None
    for tool_id in (3, 4):
        try:
            mon.use_tool_id(tool_id, "planwise-suite-deps")
        except ValueError:
            continue
        mon.register_callback(tool_id, mon.events.PY_START, _on_start)
        mon.set_events(tool_id, mon.events.PY_START)
        return tool_id
    return None


_TOOL_ID = None


def _switch(path):
    """Attribute what follows to the test file at `path`.

    sys.monitoring DISABLE is global, so each code object reports once until
    the events restart. Restarting when the file changes lets the next test
    file see code an earlier file already ran. Consecutive tests of one file
    do not restart, which keeps the overhead to one report per code object
    per file.
    """
    global _current
    rel = _rel(path)
    if rel != _current:
        _current = rel
        if _TOOL_ID is not None:
            sys.monitoring.restart_events()


def pytest_configure(config):
    global _TOOL_ID
    if not _OUT_DIR:
        return
    sys.addaudithook(_audit)
    _TOOL_ID = _claim_tool_id()


@pytest.hookimpl(wrapper=True)
def pytest_make_collect_report(collector):
    if _OUT_DIR and isinstance(collector, pytest.Module):
        _switch(collector.path)
    try:
        return (yield)
    finally:
        if _OUT_DIR and isinstance(collector, pytest.Module):
            _switch(None)


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item):
    # Teardown of the previous test stays with its own file until this
    # setup starts, because pytest tears a test down before the next setup.
    if _OUT_DIR:
        _switch(item.path)


def pytest_sessionfinish(session):
    global _current
    if not _OUT_DIR:
        return
    _current = None
    if _TOOL_ID is not None:
        sys.monitoring.set_events(_TOOL_ID, 0)
        sys.monitoring.free_tool_id(_TOOL_ID)
    data = {
        test: {"files": sorted(entry["files"]), "dirs": sorted(entry["dirs"])}
        for test, entry in _deps.items()
        if test and test.startswith("tests/")
    }
    if not data:
        return
    worker = os.environ.get("PYTEST_XDIST_WORKER", "main")
    out = Path(_OUT_DIR) / f"deps-{worker}.json"
    out.write_text(json.dumps(data, sort_keys=True), encoding="utf-8")
