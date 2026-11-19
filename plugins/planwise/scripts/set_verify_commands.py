#!/usr/bin/env python3
"""Store accepted verify commands under `build_commands.verify` in config.yaml (stdlib only).

## Usage

    python set_verify_commands.py --config <path> --command <cmd> [--command <cmd> ...]

## Behaviour

The writer changes the file only when `build_commands.verify` is absent, empty
(`verify: []` or a bare `verify:`), or `build_commands` is missing. Every other
line of the file stays as written, comments included.

| State of the config | Result | Exit |
|---|---|---|
| no `--command` given | Writes nothing | 0 |
| `build_commands.verify` holds one or more commands | Leaves the file byte-identical and says so | 0 |
| `build_commands:` block without a `verify` key | Inserts `verify:` and the list after the block's last entry | 0 |
| `verify: []` or a bare `verify:` | Fills the key with the list | 0 |
| no `build_commands` block | Appends the block at the end of the file | 0 |
| `build_commands` written as an inline mapping or scalar | Writes nothing and says so | 1 |
| config file missing | Writes nothing | 1 |
| the edited file does not parse | Rolls the write back and says so | 1 |

A command is written as a YAML block list item. A command that a plain YAML scalar
cannot hold is single-quoted. A command with a line break is refused with exit 2.
The write goes through `config_loader.write_config_checked`, which parses the result
and restores the file when it does not parse.
"""

import argparse
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # an installed plugin must not grow scripts/__pycache__
from config_loader import ConfigWriteError, find_top_level_block, write_config_checked

_VERIFY_RE = re.compile(r"^(?P<indent>[ \t]+)verify:(?P<rest>[^\n]*)$")
_NEEDS_QUOTES_RE = re.compile(r"""^[\s\-?:,\[\]{}#&*!|>'"%@`]|: |:$| #|\s$""")


def _scalar(command: str) -> str:
    """Return `command` as a YAML scalar, single-quoted when a plain scalar would misread it."""
    if _NEEDS_QUOTES_RE.search(command):
        return "'" + command.replace("'", "''") + "'"
    return command


def _items(commands: "list[str]", indent: str) -> "list[str]":
    return [f"{indent}  - {_scalar(command)}" for command in commands]


def _rest_is_empty(rest: str) -> bool:
    """True when the text after `verify:` holds no value: nothing, an empty flow list, or a comment."""
    value = re.sub(r"\s+#.*$", "", rest.strip())
    if value.startswith("#"):
        value = ""
    return value in ("", "[]", "null", "~")


def _has_children(lines: "list[str]", header: int, end: int, indent: str) -> bool:
    """True when a line below the `verify:` header at index `header` is a list item deeper than `indent`."""
    for index in range(header + 1, end):
        line = lines[index]
        if line.strip() == "" or line.lstrip().startswith("#"):
            continue
        child = re.match(r"^([ \t]+)\S", line)
        return child is not None and len(child.group(1)) > len(indent)
    return False


def splice_verify(text: str, commands: "list[str]") -> "tuple[str, str]":
    """Return (new_text, state) for storing `commands`.

    `state` is `written` when the text changed and `kept` when `verify` already holds commands.
    Raises ValueError when `build_commands` is not a block mapping.
    """
    lines = text.split("\n")
    for line in lines:
        if re.match(r"^build_commands:[ \t]*[^\s#]", line):
            raise ValueError("build_commands is not a block mapping")
    block = find_top_level_block(lines, "build_commands")
    if block is None:
        body = text if text.endswith("\n") or text == "" else text + "\n"
        added = ["build_commands:", "  verify:"] + _items(commands, "  ") + [""]
        return body + "\n".join(added), "written"

    header, end, indent = block
    for index in range(header + 1, end):
        match = _VERIFY_RE.match(lines[index])
        if match is None or match.group("indent") != indent:
            continue
        if not _rest_is_empty(match.group("rest")):
            return text, "kept"
        if _has_children(lines, index, end, indent):
            return text, "kept"
        comment = re.search(r"\s+#.*$", match.group("rest"))
        lines[index] = f"{indent}verify:" + (comment.group(0) if comment else "")
        lines[index + 1:index + 1] = _items(commands, indent)
        return "\n".join(lines), "written"

    lines[end:end] = [f"{indent}verify:"] + _items(commands, indent)
    return "\n".join(lines), "written"


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description="Store accepted verify commands under build_commands.verify.")
    parser.add_argument("--config", required=True, help="the config.yaml to edit")
    parser.add_argument("--command", action="append", default=[], help="a verify command; repeat for each one")
    args = parser.parse_args(argv)

    commands: list[str] = []
    for command in args.command:
        command = command.strip()
        if "\n" in command or "\r" in command:
            print("set_verify_commands: a command may not contain a line break", file=sys.stderr)
            return 2
        if command and command not in commands:
            commands.append(command)
    if not commands:
        print("set_verify_commands: no commands given; nothing written")
        return 0

    config = Path(args.config)
    if not config.is_file():
        print(f"set_verify_commands: config.yaml not found at {config}", file=sys.stderr)
        return 1
    text = config.read_text(encoding="utf-8")
    try:
        new_text, state = splice_verify(text, commands)
    except ValueError as exc:
        print(f"set_verify_commands: {exc}; config.yaml left unchanged", file=sys.stderr)
        return 1
    if state == "kept":
        print("build_commands.verify already holds commands; config.yaml left unchanged")
        return 0
    try:
        write_config_checked(config, new_text)
    except ConfigWriteError as exc:
        print(f"set_verify_commands: {exc}", file=sys.stderr)
        return 1
    print(f"build_commands.verify: wrote {len(commands)} command(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
