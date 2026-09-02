# Keep the shipped plugin subtree free of bytecode caches.
#
# The suite in tests/ imports modules from plugins/planwise/scripts/. Without
# this flag CPython writes plugins/planwise/scripts/__pycache__/ next to those
# modules on import, and that directory would then be copied into the
# marketplace distribution — the plugin installer copies the working tree, not
# the git-tracked set, so .gitignore does not keep it out of the shipped
# artifact. Disabling bytecode writes closes that regeneration path.
import sys
from pathlib import Path

import pytest

sys.dont_write_bytecode = True


def pytest_collection_modifyitems(
    session: pytest.Session, config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Enforce this ini's ``testpaths`` from ANY invocation directory.

    ``testpaths = tests`` in pytest.ini applies only when pytest is invoked
    FROM this directory. Invoked from a parent directory with
    ``-c <this>/pytest.ini`` (the authoring project runs it from its own
    root, where ``cd`` is denied), pytest keeps this rootdir but collects
    from the invocation directory instead — and sweeps in every
    ``test_*.py`` beneath it: plan-side harness tests a concurrent session
    may be writing at that moment, AND this repo's own ``evals/selftest/``,
    which the evals README declares deliberately unreachable from this ini
    (it has its own ``evals/pytest.ini`` and a paid runner ladder). Measured
    2026-09-01: the same plugin code reported 797, 807 and 965 within one
    session while the ``tests/`` suite moved 564 -> 591. A baseline that
    depends on the invocation directory is not a baseline.

    This hook deselects every collected item that is not under one of the
    ini's ``testpaths`` (resolved against rootpath), so every invocation
    form reports the same count; pytest shows the rest as ``N deselected``.

    Why this hook and not ``pytest_ignore_collect``: collection hooks are
    dispatched through a path-scoped proxy, so a conftest here is never
    consulted for a path outside this directory — an ignore hook was tried
    first and silently did nothing. ``pytest_collection_modifyitems`` runs
    once over the whole session's items, so it can see them all.

    Two limits. Foreign modules are still IMPORTED during collection, so a
    broken module elsewhere still reports a collection error naming its own
    path; it just never runs or counts here. And this conftest is loaded
    only once collection walks INTO this repo: an invocation whose only
    argument is a foreign path never loads it and runs exactly what was
    asked — the caller's stated intent, not a leak. The evals runner
    (``-c evals/pytest.ini evals``) uses its own rootdir, above which this
    conftest is never loaded, so it is unaffected.
    """
    root = config.rootpath.resolve()
    testpaths = config.getini("testpaths") or ["."]
    allowed = [(root / p).resolve() for p in testpaths]
    outside: list[pytest.Item] = []
    inside: list[pytest.Item] = []
    for item in items:
        path = Path(str(item.path)).resolve()
        if any(path == a or a in path.parents for a in allowed):
            inside.append(item)
        else:
            outside.append(item)
    if outside:
        config.hook.pytest_deselected(items=outside)
        items[:] = inside
