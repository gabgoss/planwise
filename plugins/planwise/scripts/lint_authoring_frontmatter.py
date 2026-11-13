#!/usr/bin/env python3
"""Frontmatter lint for rule files and skill files.

Two subcommands, each reading `---` frontmatter through `frontmatter_parser`.

`rules <path>...` checks a rule file, or every `*.md` under a folder:
  - a `description` key exists and is not empty
  - `paths`, when present, is not empty and holds none of the over-broad
    globs `**/*.md`, `*.md` or `**`
  - the file name is lowercase with hyphens
`skills <path>...` checks a `SKILL.md` file, or every `SKILL.md` under a folder:
  - the file has fewer than 500 lines (counted from the raw bytes)
  - `name`, when present, is lowercase-hyphen and at most 64 characters
  - a `description` key exists and is not empty
  - `agent:` appears only together with `context: fork`
  - every `Bash(x)` entry of `allowed-tools` has a pattern ending in a glob

Reading `paths`, `agent`, `context` and `allowed-tools` needs no second YAML
parser. `parse_frontmatter_map` returns one string per key. A list value
arrives as the key's own text with `\\n` and each `- ` item line appended, so
this script splits that string on newlines and commas and strips quotes. The
sibling `item_frontmatter` module reads backlog items with `yaml.safe_load`
and is built for typed item fields, so it is not used here.

Input: files or folders on the command line.
Output: one line per finding, `<file>:<line>: <message>`.
Exit 0 when clean, 1 when any finding prints, 2 on a usage error or an
unreadable input.

What it cannot see: whether an unscoped rule is meant to be global. A rule with
no `paths` key is global by definition, so it passes. `--report-global` lists
those rules so a reviewer can confirm the intent. It also cannot judge whether
a path list is too wide in practice, only whether it holds one of the three
named globs. A `Bash(x)` entry written inside a multi-line YAML block scalar
that does not use `Bash(` at the start of an item is still found, because the
scan reads the whole `allowed-tools` text.

Enforces references/rule-authoring.md sections 1, 2 and 4, and
references/skill-authoring.md sections 1, 2, 5b and 7b.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse
import re
from pathlib import Path

from frontmatter_parser import parse_frontmatter_map, split_frontmatter_block

BROAD_PATHS = ("**/*.md", "*.md", "**")
RULE_NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*\.md$")
SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
BASH_ENTRY_RE = re.compile(r"Bash\(([^)]*)\)")
SKILL_LINE_LIMIT = 500
SKILL_NAME_MAX = 64


def _read(path: Path) -> str:
    """Read a file as UTF-8 text with LF endings. Raises OSError or ValueError."""
    raw = path.read_bytes()
    return raw.decode("utf-8").replace("\r\n", "\n")


def _count_lines(path: Path) -> int:
    """Count lines from the raw bytes, never from decoded characters."""
    raw = path.read_bytes()
    count = raw.count(b"\n")
    if raw and not raw.endswith(b"\n"):
        count += 1
    return count


def _unquote(text: str) -> str:
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    return text


def _list_items(value: str) -> list[str]:
    """Split a `paths`-style value into items. Handles inline and `- ` lists."""
    items: list[str] = []
    for line in value.split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith("- "):
            items.append(_unquote(line[2:]))
        elif line == "-":
            continue
        else:
            items.extend(_unquote(part) for part in line.split(",") if part.strip())
    return items


def _key_line(frontmatter: str, key: str) -> int:
    """1-based file line of a top-level key, or 2 when the key is absent."""
    for index, line in enumerate(frontmatter.split("\n")):
        if line.startswith(key + ":"):
            return index + 2
    return 2


def _load(path: Path) -> tuple[str, dict[str, str] | None, str]:
    """Return (frontmatter text or '', parsed map or None, status)."""
    content = _read(path)
    block = split_frontmatter_block(content)
    if block is None:
        return "", None, "none"
    fm_text, _body = block
    fm_map = parse_frontmatter_map(fm_text)
    if fm_map is None:
        return fm_text, None, "unparseable"
    return fm_text, fm_map, "ok"


def lint_rule(path: Path, report_global: list[str]) -> list[str]:
    """Return the findings of one rule file."""
    findings: list[str] = []
    if not RULE_NAME_RE.match(path.name):
        findings.append(f"{path}:1: rule file name is not lowercase with hyphens")
    fm_text, fm_map, status = _load(path)
    if status == "none":
        findings.append(f"{path}:1: no frontmatter block, so no description")
        return findings
    if fm_map is None:
        findings.append(f"{path}:2: frontmatter cannot be parsed")
        return findings
    if not fm_map.get("description", "").strip():
        findings.append(f"{path}:{_key_line(fm_text, 'description')}: missing description")
    if "paths" not in fm_map:
        report_global.append(f"{path}: no paths key, treated as a global rule")
    else:
        line = _key_line(fm_text, "paths")
        items = _list_items(fm_map["paths"])
        if not items:
            findings.append(f"{path}:{line}: paths is empty")
        for item in items:
            if item in BROAD_PATHS:
                findings.append(f"{path}:{line}: paths holds the over-broad glob {item}")
    return findings


def lint_skill(path: Path) -> list[str]:
    """Return the findings of one SKILL.md file."""
    findings: list[str] = []
    lines = _count_lines(path)
    if lines >= SKILL_LINE_LIMIT:
        findings.append(f"{path}:1: SKILL.md has {lines} lines, the limit is under {SKILL_LINE_LIMIT}")
    fm_text, fm_map, status = _load(path)
    if status == "none":
        findings.append(f"{path}:1: no frontmatter block, so no description")
        return findings
    if fm_map is None:
        findings.append(f"{path}:2: frontmatter cannot be parsed")
        return findings
    if "name" in fm_map:
        name = _unquote(fm_map["name"])
        if not SKILL_NAME_RE.match(name):
            findings.append(f"{path}:{_key_line(fm_text, 'name')}: name {name!r} is not lowercase-hyphen")
        if len(name) > SKILL_NAME_MAX:
            findings.append(f"{path}:{_key_line(fm_text, 'name')}: name is {len(name)} characters, the limit is {SKILL_NAME_MAX}")
    if not fm_map.get("description", "").strip():
        findings.append(f"{path}:{_key_line(fm_text, 'description')}: missing description")
    if "agent" in fm_map and _unquote(fm_map.get("context", "")) != "fork":
        findings.append(f"{path}:{_key_line(fm_text, 'agent')}: agent is set without context: fork")
    for pattern in BASH_ENTRY_RE.findall(fm_map.get("allowed-tools", "")):
        if not pattern.endswith("*"):
            findings.append(
                f"{path}:{_key_line(fm_text, 'allowed-tools')}: Bash({pattern}) pattern does not end in a glob"
            )
    return findings


def _expand(arg: str, kind: str) -> list[Path]:
    """Expand one argument to files. Raises FileNotFoundError when absent."""
    path = Path(arg)
    if path.is_dir():
        pattern = "*.md" if kind == "rules" else "SKILL.md"
        return sorted(path.rglob(pattern))
    if path.is_file():
        return [path]
    raise FileNotFoundError(arg)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lint rule and skill frontmatter.")
    parser.add_argument("kind", choices=("rules", "skills"))
    parser.add_argument("paths", nargs="+")
    parser.add_argument("--report-global", action="store_true", help="list rules with no paths key")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return 2 if exc.code else 0
    findings: list[str] = []
    report_global: list[str] = []
    seen = 0
    try:
        for arg in args.paths:
            for path in _expand(arg, args.kind):
                seen += 1
                if args.kind == "rules":
                    findings.extend(lint_rule(path, report_global))
                else:
                    findings.extend(lint_skill(path))
    except (OSError, ValueError) as exc:
        print(f"error: cannot read input: {exc}", file=sys.stderr)
        return 2
    if seen == 0:
        print("error: no files found under the given paths", file=sys.stderr)
        return 2
    for line in findings:
        print(line)
    if args.report_global:
        for line in report_global:
            print(f"note: {line}")
    print(f"checked {seen} file(s), {len(findings)} finding(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
