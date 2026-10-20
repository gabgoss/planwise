"""The installed plugin must never hold bytecode or development artifacts.

A consumer's install cache is a copy of `plugins/planwise/`, and the handlers
run the scripts from that copy. CPython writes `scripts/__pycache__/` next to
every sibling module an entry script imports, so an install grew one on first
use. Every entry script therefore sets `sys.dont_write_bytecode = True` before
its first sibling import.

Three checks follow. The first reads each entry script's syntax tree for the
flag and its position. The second runs each entry script from a scratch copy of
the plugin, with bytecode writing on in the environment, and requires the copy
to stay clean. The third walks the shipped subtree on disk, not through git,
because `.gitignore` hides a cache directory from git but not from the copy.
"""
import ast
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parent.parent / "plugins" / "planwise"
SCRIPTS = PLUGIN / "scripts"
SIBLINGS = {p.stem for p in SCRIPTS.glob("*.py")}

# Extra argv per script, where `--help` alone would never reach a sibling import.
# skill_preflight imports list_plans only for the `list` subcommand.
RUN_ARGS = {"skill_preflight": ["list"]}

CACHE_DIRS = {"__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache"}


def _is_main_guard(node: ast.stmt) -> bool:
    return (isinstance(node, ast.If) and isinstance(node.test, ast.Compare)
            and isinstance(node.test.left, ast.Name) and node.test.left.id == "__name__"
            and any(isinstance(c, ast.Constant) and c.value == "__main__" for c in node.test.comparators))


def _entry_scripts() -> list[str]:
    return sorted(p.stem for p in SCRIPTS.glob("*.py")
                  if any(_is_main_guard(n) for n in ast.parse(p.read_text(encoding="utf-8")).body))


ENTRY_SCRIPTS = _entry_scripts()


def _sets_flag(node: ast.stmt) -> bool:
    return (isinstance(node, ast.Assign) and len(node.targets) == 1
            and ast.unparse(node.targets[0]) == "sys.dont_write_bytecode"
            and isinstance(node.value, ast.Constant) and node.value.value is True)


def _imports_sibling(node: ast.stmt) -> bool:
    if isinstance(node, ast.Import):
        return any(a.name.split(".")[0] in SIBLINGS for a in node.names)
    if isinstance(node, ast.ImportFrom):
        return node.level == 0 and (node.module or "").split(".")[0] in SIBLINGS
    return False


def _bytecode_under(root: Path) -> list[str]:
    hits = []
    for dirpath, dirnames, filenames in os.walk(root):
        hits += [os.path.join(dirpath, d) for d in dirnames if d == "__pycache__"]
        hits += [os.path.join(dirpath, f) for f in filenames if f.endswith(".pyc")]
    return hits


def _bytecode_env() -> dict:
    # The authoring project sets PYTHONDONTWRITEBYTECODE for its own sessions.
    # Drop it, so the run below shows what a consumer's interpreter does.
    return {k: v for k, v in os.environ.items() if k != "PYTHONDONTWRITEBYTECODE"}


def test_the_entry_script_scan_sees_the_scripts_directory():
    # An empty scan would parametrize zero cases and pass vacuously.
    assert {"init_project", "parse_backlog", "skill_preflight"} <= set(ENTRY_SCRIPTS), ENTRY_SCRIPTS


@pytest.mark.parametrize("script", ENTRY_SCRIPTS)
def test_entry_script_turns_bytecode_off_before_any_sibling_import(script):
    body = ast.parse((SCRIPTS / f"{script}.py").read_text(encoding="utf-8")).body
    flag = next((i for i, n in enumerate(body) if _sets_flag(n)), None)
    assert flag is not None, f"{script}.py never sets sys.dont_write_bytecode = True at module level"
    first_import = next((i for i, n in enumerate(body) if _imports_sibling(n)), len(body))
    assert flag < first_import, f"{script}.py imports a sibling at line {body[first_import].lineno} before the flag"


@pytest.fixture(scope="module")
def plugin_copy(tmp_path_factory):
    root = tmp_path_factory.mktemp("installed") / "planwise"
    shutil.copytree(PLUGIN, root, ignore=shutil.ignore_patterns(*CACHE_DIRS, "*.pyc"))
    return root


def test_the_environment_writes_bytecode_without_the_flag(plugin_copy, tmp_path):
    # Positive control: without the flag this interpreter does write bytecode,
    # so a clean copy in the next test is evidence and not a quiet environment.
    control = tmp_path / "control"
    shutil.copytree(plugin_copy / "scripts", control)
    code = f"import sys; sys.path.insert(0, {str(control)!r}); import constants"
    subprocess.run([sys.executable, "-c", code], env=_bytecode_env(), check=True, timeout=60)
    assert _bytecode_under(control)


def test_running_each_entry_script_leaves_no_bytecode(plugin_copy, tmp_path):
    offenders = {}
    for script in ENTRY_SCRIPTS:
        argv = RUN_ARGS.get(script, ["--help"])
        subprocess.run([sys.executable, str(plugin_copy / "scripts" / f"{script}.py"), *argv],
                       cwd=str(tmp_path), env=_bytecode_env(), stdin=subprocess.DEVNULL,
                       capture_output=True, check=False, timeout=120)
        hits = _bytecode_under(plugin_copy)
        if hits:
            offenders[script] = hits
            # Clear the hits so the next script is judged on its own run.
            for hit in hits:
                if os.path.isdir(hit):
                    shutil.rmtree(hit)
                elif os.path.exists(hit):
                    os.remove(hit)
    assert offenders == {}


def test_shipped_subtree_on_disk_holds_no_cache_or_test_files():
    walked = 0
    hits = []
    for dirpath, dirnames, filenames in os.walk(PLUGIN):
        walked += len(filenames)
        hits += [os.path.join(dirpath, d) for d in dirnames if d in CACHE_DIRS or d.startswith("probe_")]
        hits += [os.path.join(dirpath, f) for f in filenames
                 if f.endswith(".pyc") or f == "conftest.py"
                 or (f.endswith(".py") and (f.startswith("test_") or f.endswith("_test.py")))]
    assert walked > 100, f"the walk saw only {walked} files under {PLUGIN}"
    assert hits == []
