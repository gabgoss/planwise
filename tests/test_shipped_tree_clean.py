"""The shipped subtree holds no test file, cache directory or `probe_*` directory.

The installer copies the working tree, so a stray artifact under
`plugins/planwise` ships. The walk uses an absolute path resolved from this
file and asserts it saw files, so an unresolved path fails instead of passing.

`conftest.py` sets `sys.dont_write_bytecode`, so a pytest run does not dirty
the tree it checks. A cache directory left by a non-pytest import makes this
test fail, which is the intended signal: delete it and re-run.

`SHIPPED_TREE_ROOT` repoints the walk at another tree (used by the must-fail
control).
"""
import fnmatch
import os
from pathlib import Path

ROOT = Path(
    os.environ.get("SHIPPED_TREE_ROOT")
    or Path(__file__).resolve().parent.parent / "plugins" / "planwise"
)

BAD_FILES = ("test_*.py", "*_test.py", "conftest.py")
BAD_DIRS = ("__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache", "probe_*")


def walk(root):
    """Return (files_seen, offending paths)."""
    seen = 0
    offenders = []
    for dirpath, dirnames, filenames in os.walk(root):
        seen += len(filenames)
        for d in dirnames:
            if any(fnmatch.fnmatch(d, p) for p in BAD_DIRS):
                offenders.append(os.path.join(dirpath, d))
        for f in filenames:
            if any(fnmatch.fnmatch(f, p) for p in BAD_FILES):
                offenders.append(os.path.join(dirpath, f))
    return seen, offenders


def test_the_walk_sees_the_shipped_tree():
    seen, _ = walk(ROOT)
    assert seen > 0, f"walk saw no files under {ROOT}"


def test_shipped_tree_has_no_test_files_caches_or_probe_dirs():
    _, offenders = walk(ROOT)
    assert not offenders, "leak in shipped tree: " + ", ".join(sorted(offenders))
