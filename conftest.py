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
    """Deselect every collected test that lives outside this repository.

    ``testpaths`` in pytest.ini applies only when pytest is invoked FROM this
    directory. Invoked from a parent directory with ``-c <this>/pytest.ini``
    (the authoring project runs it from its own root, where ``cd`` is denied),
    pytest keeps this rootdir but collects from the invocation directory
    instead — and sweeps in every ``test_*.py`` beneath it, including
    plan-side harness tests a concurrent session may be writing at that
    moment. Measured 2026-09-01: the same plugin code reported 797, 807 and
    965 within one session while this repo's own suite moved 564 -> 591. A
    baseline that depends on what happens to live next to the repo is not a
    baseline.

    Why this hook and not ``pytest_ignore_collect``: collection hooks are
    dispatched through a path-scoped proxy, so a conftest here is never
    consulted for a path outside this directory — an ignore hook was tried
    first and silently did nothing. ``pytest_collection_modifyitems`` runs
    once over the whole session's items, so it can see them all.

    Two limits, both measured 2026-09-01. Foreign modules are still IMPORTED
    during collection, so a broken module elsewhere still reports a
    collection error naming its own path; it just never runs or counts here
    (from the authoring project root: ``707 passed, 310 deselected`` — the
    707 being ``tests/`` plus ``evals/selftest/``). And this conftest is only
    loaded once collection walks INTO this repo: an invocation whose only
    argument is a foreign path (``-c <this>/pytest.ini some/other/tests``)
    never loads it and runs exactly what was asked — the caller's stated
    intent, not a leak. The prescribed baseline command scopes the run to
    ``tests/`` explicitly (591 passed) and is unaffected by this hook.
    """
    root = config.rootpath.resolve()
    outside: list[pytest.Item] = []
    inside: list[pytest.Item] = []
    for item in items:
        path = Path(str(item.path)).resolve()
        if path == root or root in path.parents:
            inside.append(item)
        else:
            outside.append(item)
    if outside:
        config.hook.pytest_deselected(items=outside)
        items[:] = inside
