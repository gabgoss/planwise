#!/usr/bin/env python3
"""Build the command that installs PyYAML into the interpreter running a script.

The bare pip form installs into whichever interpreter `pip` resolves to on
PATH, which is often not the one that just failed to import PyYAML. This
module returns the install command that targets the right environment:

  * `uv.lock` in the project root     -> `uv add --dev pyyaml`
  * `poetry.lock` in the project root -> `poetry add --group dev pyyaml`
  * `Pipfile.lock` in the project root -> `pipenv install --dev pyyaml`
  * otherwise the explicit-interpreter pip form, naming `sys.executable`

Standard library only, so any script may import it without a cycle.
"""

import sys
from pathlib import Path

# Lock file name -> install command, checked in this order.
_MANAGER_COMMANDS = (
    ("uv.lock", "uv add --dev pyyaml"),
    ("poetry.lock", "poetry add --group dev pyyaml"),
    ("Pipfile.lock", "pipenv install --dev pyyaml"),
)


def pyyaml_install_command(project_root: Path) -> str:
    """Return the manager-correct PyYAML install command for `project_root`."""
    for lock_name, command in _MANAGER_COMMANDS:
        if (Path(project_root) / lock_name).is_file():
            return command
    return f'"{sys.executable}" -m pip install pyyaml'
