"""Every shipped script module must import cleanly as the FIRST import of a
fresh interpreter.

Inside one pytest process, whichever test module imports first decides the
order every script module is initialised in, so an import cycle can stay
hidden. `init_project`, the composition root, re-exports names from
`artifact_upgrade` and `rule_descope_migration`, and both (plus
`doctor_sweeps` and `doctor_cli`) import back from `init_project`. The root
conftest imports only `sys`, `pathlib` and `pytest`, so nothing there hides
the defect; collection order does. Each case therefore runs in a subprocess
with bytecode off (`-B`), where nothing has been imported yet.

The module list is a glob of `plugins/planwise/scripts/*.py`, so a new
module is covered without editing this file.
"""
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"

# Modules that legitimately cannot be imported standalone, each with the
# reason. Empty: every shipped module imports first in a fresh interpreter.
EXCLUDED: dict = {}

MODULES = sorted(p.stem for p in SCRIPTS.glob("*.py") if p.stem not in EXCLUDED)


def test_the_glob_sees_the_scripts_directory():
    # An empty glob would parametrize zero cases and pass vacuously.
    assert "init_project" in MODULES, MODULES


@pytest.mark.parametrize("module", MODULES)
def test_module_imports_first_in_a_fresh_interpreter(module):
    code = f"import sys; sys.path.insert(0, {str(SCRIPTS)!r}); import {module}"
    result = subprocess.run(
        [sys.executable, "-B", "-c", code],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
