"""Each module in the init_project / artifact_upgrade / rule_descope_migration
cycle must import cleanly as the FIRST import of a fresh interpreter.

pytest's own conftest imports `init_project` before anything else, which
hides an ordering defect: the composition root re-exports names from
`artifact_upgrade` and `rule_descope_migration`, and both import back from
`init_project`. So each case runs in a subprocess with bytecode off (`-B`),
where nothing has been imported yet.
"""
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"


@pytest.mark.parametrize("module", [
    "artifact_upgrade",
    "promotion_log",
    "lessons_changelog",
    "init_project",
    "rule_descope_migration",
])
def test_module_imports_first_in_a_fresh_interpreter(module):
    code = f"import sys; sys.path.insert(0, {str(SCRIPTS)!r}); import {module}"
    result = subprocess.run(
        [sys.executable, "-B", "-c", code],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
